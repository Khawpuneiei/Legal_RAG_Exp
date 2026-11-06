"""TaxRAG answers: the teammate's generation step (his prompt, numbered sources, citation rewriting and
refusal rule, rag.generate) fed by his `improved` retrieval or by the Experiment 3 pipeline.

The model is local (qwen2.5:7b through Ollama) for every configuration, so differences come from retrieval,
evidence selection and the abstention gate only. His app uses Groq gpt-oss-120b; absolute answer quality
here is lower, the comparison between configurations is what this measures. `--model groq` answers with his
app's own model instead (rag.llm.GroqChat: gpt-oss-120b, his settings) on GROQ_API_KEY, `--model gemini` with its
fallback (rag.llm.GeminiChat) on GEMINI_API_KEY: one call per question and configuration, cached, so a rerun or a
resumed run spends nothing on what it already has. A daily quota stops the run; per-minute limits and 5xx wait.

    python eval/tax_generation.py            # -> eval/results/tax/generation_per_question.jsonl, generation_summary.md
    python eval/tax_generation.py --split dev --configs R6x@gemini ...   # the held-out dev split, chosen configs
    python eval/tax_generation.py --model gemini --configs teammate-improved@gemini R6y@gemini --dry-run   # counts only
    python eval/tax_generation.py --model gemini --configs teammate-improved@gemini R6y@gemini   # -> *_gemini files
    python eval/tax_generation.py --model groq --configs teammate-improved@gemini R6y@gemini     # -> *_groq files
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.tax_experiment import OUT, Runner, load_keys  # noqa: E402
from eval.tax_report import _fmt_diff, paired  # noqa: E402
from src.common import CACHE, JsonCache, read_jsonl, stable_hash  # noqa: E402
from src.llm.ollama import OllamaLLM  # noqa: E402
from src.tax.graph import TaxGraph  # noqa: E402
from src.tax.corpus import chunks  # noqa: E402

MODEL = "qwen2.5:7b"
# Local reasoning models, a stand-in for his gpt-oss-120b: Ollama returns their reasoning apart from the answer,
# and like his app the cap of 2,000 output tokens includes it (rag.llm.MAX_ANSWER_TOKENS).
REASONING = {"qwen3:8b": 2000}
ANSWERS = CACHE / "tax" / "generation_answers.jsonl"
# (A, B, question): paired over the held-out test split's answerable questions
COMPARISONS = [
    ("R6x@gemini", "teammate-improved@gemini", "A* dependencies in place of his expansion, his deployed setup otherwise"),
    ("R6y@gemini", "teammate-improved@gemini", "dependency-only A* in place of his expansion, his deployed setup otherwise"),
    ("R6d@gemini", "teammate-improved@gemini", "A* evidence in place of his whole context, on his Gemini ranking"),
    ("teammate-improved@gemini+gate", "teammate-improved@gemini", "the abstention gate on his deployed retrieval"),
    ("R5@budget", "teammate-improved@bge-m3", "Experiment 3 retrieval (R5) vs his `improved`, same local embedder"),
    ("R5+expand", "teammate-improved@bge-m3", "R5 vs his `improved`, same local embedder and context layout (hits + his expansion)"),
    ("R5@budget", "R5+expand", "his one-hop expansion removed, R5 hits"),
    ("R6x", "R5+expand", "A* dependencies vs his expansion, after the R5 hits"),
    ("R6d", "R5@budget", "A* evidence vs flat R5, same budget"),
    ("R6d+gate", "R6d", "the abstention gate on R6d"),
]
SETS = [("reference", None, "Teammate's 28 questions"), ("heldout", "test", "Held-out test split"),
        ("heldout", "dev", "Held-out dev split (run after the first test run, to check the R6x variant on unseen answers)")]


class OllamaChat:
    """The teammate's ChatModel protocol (rag.llm) on a local model."""

    def __init__(self, model: str = MODEL, max_tokens: int = 700, num_ctx: int = 8192):
        self.llm = OllamaLLM(model, num_ctx=num_ctx, cache_name="tax-answers")
        self.name, self.max_tokens = f"ollama:{model}", max_tokens

    def complete(self, system: str, user: str) -> str:
        return self.llm.generate(user, system=system, max_tokens=self.max_tokens)["text"]


TRANSIENT_RETRIES = 6   # per answer, after the SDK's own retries: on 5xx and per-minute rate limits only


def transient(error: Exception) -> bool:
    """A server error or a per-minute limit (worth waiting for), not a daily quota (which stops the run)."""
    code = getattr(error, "code", None) or getattr(error, "status_code", None)
    if code in (500, 502, 503, 504):
        return True
    text = str(error)
    return code == 429 and not any(m in text for m in ("PerDay", "per day", "(TPD)", "(RPD)"))


class CallCap(RuntimeError):
    pass


class CachedChat:
    """A ChatModel (his GeminiChat) with a disk cache, a request-rate limit and a cap on new calls."""

    def __init__(self, model, rpm: float, max_calls: int | None = None):
        self.model, self.name = model, model.name
        self.cache = JsonCache("tax-answers-" + model.name.replace(":", "_").replace("/", "_"))
        self.interval, self.max_calls, self.calls, self.next_at = 60.0 / rpm, max_calls, 0, 0.0
        self.lock = threading.Lock()

    def key(self, system: str, user: str) -> str:
        return stable_hash(self.name, system, user)

    def complete(self, system: str, user: str) -> str:
        key = self.key(system, user)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        for attempt in range(TRANSIENT_RETRIES + 1):
            with self.lock:   # reserve a start time; the calls themselves may overlap
                if self.max_calls is not None and self.calls >= self.max_calls:
                    raise CallCap(f"--max-calls {self.max_calls} reached")
                start = max(time.monotonic(), self.next_at)
                self.next_at = start + self.interval
            time.sleep(max(0.0, start - time.monotonic()))
            t0 = time.monotonic()
            try:
                text = self.model.complete(system, user)
                break
            except Exception as error:   # "high demand" 5xx or a per-minute limit after the SDK's retries: wait, retry
                if not transient(error) or attempt == TRANSIENT_RETRIES:
                    raise
                code = getattr(error, "code", None) or getattr(error, "status_code", "")
                print(f"  {code} after {time.monotonic() - t0:.0f}s; waiting {60 * (attempt + 1)}s", flush=True)
                time.sleep(60 * (attempt + 1))
        with self.lock:   # only answers count towards --max-calls
            self.calls += 1
            self.cache.put(key, text)
            print(f"  call {self.calls}: {time.monotonic() - t0:.0f}s, {len(text)} chars", flush=True)
        return text


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--split", choices=["test", "dev"], default="test",
                    help="test: the teammate's 28 questions and the held-out test split; dev: the held-out dev split")
    ap.add_argument("--configs", nargs="*", default=None)
    ap.add_argument("--model", choices=[MODEL, *REASONING, "groq", "gemini"], default=MODEL,
                    help="qwen3:8b: a local reasoning model; groq / gemini: his app's chat model / its fallback (rag.llm). "
                         "Results in *_qwen3-8b / *_groq / *_gemini files")
    ap.add_argument("--rpm", type=float, default=8.0, help="groq, gemini: requests per minute at most")
    ap.add_argument("--max-calls", type=int, default=None, help="groq, gemini: stop after this many new answers")
    ap.add_argument("--dry-run", action="store_true", help="count the model calls and prompt sizes; call nothing")
    ap.add_argument("--num-ctx", type=int, default=8192, help="local models: context window (part of the answer cache key)")
    ap.add_argument("--suffix", default=None, help="output file suffix (default: from --model)")
    args = ap.parse_args()
    load_keys()
    runner = Runner()
    rag = runner.rag
    gen = rag.generate
    llm = __import__("rag.llm", fromlist=["GeminiChat"])
    suffix = args.suffix if args.suffix is not None else "" if args.model == MODEL else "_" + args.model.replace(":", "-")
    if args.model == MODEL:
        chat = OllamaChat(num_ctx=args.num_ctx)
    elif args.model in REASONING:
        chat = OllamaChat(args.model, REASONING[args.model], args.num_ctx)
    else:
        chat = CachedChat(llm.GroqChat() if args.model == "groq" else llm.GeminiChat(), args.rpm, args.max_calls)
    gate = json.loads((OUT / "gate.json").read_text(encoding="utf-8"))
    tuning = json.loads((OUT / "graph_tuning.json").read_text(encoding="utf-8"))   # {seed condition: {grid, best, expand}}
    s5 = runner.search("bge-m3", True)
    graphs = {"R5": (s5, TaxGraph(chunks("structured"), s5.doc_vectors, rag.chunk.count_tokens))}
    plain = runner.search("bge-m3", False)
    configs = ["teammate-improved@bge-m3", "R5@budget", "R6d", "R6d+gate", "R5+expand", "R6x"]
    try:   # the teammate's deployed retrieval: his Gemini index
        gem = runner.search("gemini", False)
        graphs["structured_routed@gemini"] = (gem, TaxGraph(chunks("structured"), gem.doc_vectors, rag.chunk.count_tokens))
        configs += ["teammate-improved@gemini", "teammate-improved@gemini+gate", "R6d@gemini", "R6x@gemini", "R6y@gemini"]
    except rag.embed.MissingApiKey:
        gem = None
    configs = [c for c in configs if args.configs is None or c in args.configs]
    if args.split == "test":
        questions = [q for q in runner.questions if q.qset == "reference" or q.split == "test"]
    else:
        questions = [q for q in runner.questions if q.qset == "heldout" and q.split == "dev"]

    def astar(seed: str, ranked: list, q) -> list:
        search, graph = graphs[seed]
        best, ids = tuning[seed]["best"], [c.chunk_id for c in ranked]
        out = graph.graph.astar(ids[:best["seeds"]], search.query_embedder.embed_query(q.question), runner.budget,
                                lam=best["lam"], mu=best["mu"])
        return [graph.chunks[c] for c in graph.fill(out["evidence"], ids, runner.budget)]

    def astar_after(seed: str, hits: list, q, dependencies_only: bool = False) -> list:
        """R6x: the hits, then what A* picks for them in place of the teammate's expansion (R6y: dependency edges only)."""
        search, graph = graphs[seed]
        x = tuning[seed]["expand_dep" if dependencies_only else "expand"]
        extra = graph.expand([c.chunk_id for c in hits], search.query_embedder.embed_query(q.question), x["allowance"],
                             x["best"]["lam"], x["best"]["mu"], follow_seed_only=not dependencies_only)
        return list(hits) + [graph.chunks[c] for c in extra]

    def sources_for(config: str, q) -> tuple[list, bool]:
        """(numbered sources, refused by the gate before any model call)"""
        on_gemini = "@gemini" in config
        if config.startswith("teammate-improved") or config in ("R6x@gemini", "R6y@gemini"):
            # his `improved`: 2,500 tokens + up to 3 cross-referenced sections (R6x: A*'s dependencies instead)
            result = (gem if on_gemini else plain).retriever.search(q.question, "improved", budget=runner.budget)
            hits = [h.chunk for h in result.hits]
            seed = "structured_routed@gemini" if on_gemini else "structured_routed@bge-m3"
            if config in ("R6x@gemini", "R6y@gemini"):
                sources = astar_after(seed, hits, q, dependencies_only=config == "R6y@gemini")
            else:
                sources = hits + result.expanded
            top = runner.ranked(seed, q)[1]   # best cosine similarity: the gate's confidence without a reranker
        elif on_gemini:
            seed = "structured_routed@gemini"
            ranked, top = runner.ranked(seed, q)
            sources = astar(seed, ranked, q)
        else:
            seed = "R5"
            ranked, top = runner.ranked(seed, q)
            hits = rag.retrieve.within_budget(ranked, runner.budget)
            if config.startswith("R5@budget"):
                sources = hits
            elif config == "R5+expand":
                sources = hits + s5.retriever.corpus("structured").expand(hits)
            elif config == "R6x":
                sources = astar_after(seed, hits, q)
            else:
                sources = astar(seed, ranked, q)
        gated = config.endswith("+gate") and top is not None and top < gate[seed]["tau"]
        return sources, gated

    jobs = [(c, q) for q in questions for c in configs]   # question by question, so a partial run is still paired
    prepared = {(c, q.qset, q.id): sources_for(c, q) for c, q in jobs}   # retrieval first (GPU reranker), single-threaded
    if args.dry_run:
        prompts = [gen.build_prompt(q.question, prepared[(c, q.qset, q.id)][0]) for c, q in jobs
                   if prepared[(c, q.qset, q.id)][0] and not prepared[(c, q.qset, q.id)][1]]
        new = [p for p in prompts if not isinstance(chat, CachedChat) or chat.cache.get(chat.key(gen.SYSTEM_PROMPT, p)) is None]
        size = [rag.chunk.count_tokens(gen.SYSTEM_PROMPT + "\n" + p) for p in new]
        print(f"{len(jobs)} answers ({len(configs)} configs x {len(questions)} questions): {len(prompts)} need a model call, "
              f"{len(new)} of them not cached; prompts of {np.mean(size) if size else 0:.0f} word tokens on average, "
              f"{sum(size):,} in all; output capped at {llm.MAX_ANSWER_TOKENS} tokens each, thinking included")
        return
    stop = threading.Event()

    def one(args):
        config, q = args
        sources, gated = prepared[(config, q.qset, q.id)]
        if gated or not sources:
            return config, q, gen.Answer(q.question, gen.REFUSAL, sources, refused=True, config=config), gated
        if stop.is_set():
            return None
        try:
            raw = chat.complete(gen.SYSTEM_PROMPT, gen.build_prompt(q.question, sources))
        except (CallCap, *llm.PROVIDER_ERRORS) as error:   # quota, outage or the cap: keep what is done, resume later
            if not stop.is_set():
                print(f"stopped: {type(error).__name__}: {error}", flush=True)
            stop.set()
            return None
        text, cited, invalid = gen.render_citations(raw, sources)
        refused = not cited
        return config, q, gen.Answer(q.question, gen.REFUSAL if refused else text, sources, cited, refused, chat.name, invalid, raw, config), False

    rows, texts = [], []
    with cf.ThreadPoolExecutor(4 if args.model == MODEL else 1 if args.model in REASONING else 3) as ex:
        for result in ex.map(one, jobs):
            if result is None:
                continue
            config, q, ans, gated = result
            texts.append(dict(qset=q.qset, qid=q.id, condition=config, text=ans.text, raw=ans.raw,
                              sources=[c.chunk_id for c in ans.sources]))
            prec = rag.evaluate.citation_precision(ans.cited, q.gold_units, runner.sp) if q.answerable else None
            hit = set().union(*(rag.evaluate.units_hit(c, q.gold_units, runner.sp) for c in ans.cited)) if ans.cited else set()
            rows.append(dict(qset=q.qset, split=q.split, qid=q.id, type=q.type, answerable=q.answerable, condition=config,
                             refused=ans.refused, gated=gated, model_called=bool(ans.model), n_sources=len(ans.sources),
                             source_tokens=sum(rag.chunk.count_tokens(c.text) for c in ans.sources), n_cited=len(ans.cited),
                             invalid_citations=len(ans.invalid_citations), citation_precision=prec,
                             gold_cited=(len(hit) / len(q.gold_units)) if q.answerable else None,
                             cited=[c.chunk_id for c in ans.cited]))
    done = {(r["condition"], r["qset"], r["qid"]) for r in rows}
    merge(OUT / f"generation_per_question{suffix}.jsonl", rows, done)
    merge(ANSWERS.with_name(f"{ANSWERS.stem}{suffix}.jsonl"), texts, done)   # answer texts paraphrase IRAS guides: not in the repo
    summary(suffix=suffix, model=chat.name)
    if stop.is_set():
        print(f"{len(jobs) - len(rows)} answers not done; rerun the same command to resume (the done ones are cached)")
        sys.exit(1)


def merge(path, new: list[dict], done: set) -> None:
    """Rewrite `path` with these (condition, question) rows replaced and every other row kept."""
    old = [r for r in read_jsonl(path) if (r["condition"], r["qset"], r["qid"]) not in done] if path.exists() else []
    with open(path, "w", encoding="utf-8") as f:
        for r in old + new:
            f.write(json.dumps(r) + "\n")


def summary(rows: list[dict] | None = None, suffix: str = "", model: str = f"ollama:{MODEL}") -> None:
    rows = rows or read_jsonl(OUT / f"generation_per_question{suffix}.jsonl")
    for r in rows:   # per answerable question: answered at all, and gold units cited with a refusal counted as 0
        if r["answerable"]:
            r["answered"] = float(not r["refused"])
            r["gold_cited_all"] = 0.0 if r["refused"] else r["gold_cited"]
    lines = [f"# TaxRAG answers ({model.split(':', 1)[-1]}, the teammate's prompt and citation checker)", "",
             "Citation precision: share of an answer's citations that point at a gold unit (his metric). Gold cited: share of the "
             "question's gold units the answer cites, over answered answerable questions. Gold cited (all): the same over every "
             "answerable question, a refusal counting as 0, so a configuration cannot score higher by answering less.", ""]
    for qset, split, title in SETS:
        sub = [r for r in rows if r["qset"] == qset and (split is None or r["split"] == split)]
        if not sub:
            continue
        lines += [f"## {title}", "", "| Configuration | Answerable answered | Out-of-scope refused | Citation precision | Gold cited | "
                  "Gold cited (all) | Model calls | Source tokens |", "|---|---|---|---|---|---|---|---|"]
        for c in dict.fromkeys(r["condition"] for r in sub):
            rs = [r for r in sub if r["condition"] == c]
            ans = [r for r in rs if r["answerable"]]
            oos = [r for r in rs if not r["answerable"]]
            done = [r for r in ans if not r["refused"]]
            prec = [r["citation_precision"] for r in done if r["citation_precision"] is not None]
            lines.append(f"| `{c}` | {len(done)}/{len(ans)} | {sum(r['refused'] for r in oos)}/{len(oos)} | "
                         f"{np.mean(prec):.3f} | {np.mean([r['gold_cited'] for r in done]):.3f} | "
                         f"{np.mean([r['gold_cited_all'] for r in ans]):.3f} | {sum(r['model_called'] for r in rs)}/{len(rs)} | "
                         f"{np.mean([r['source_tokens'] for r in rs]):.0f} |")
        lines.append("")
        answerable = [r for r in sub if r["answerable"]]
        present = {r["condition"] for r in answerable}
        comps = [(a, b, what) for a, b, what in COMPARISONS if a in present and b in present]
        if comps:
            lines += ["Paired over the answerable questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A better / worse. "
                      "**Bold**: the CI excludes 0.", "",
                      "| A | B | Question | Metric | Mean A − B [95% CI] | Wilcoxon p | A better / worse |", "|---|---|---|---|---|---|---|"]
            for a, b, what in comps:
                for m, label in [("gold_cited_all", "gold cited (all)"), ("answered", "answered")]:
                    s, p, wl = _fmt_diff(paired(answerable, a, b, m))
                    lines.append(f"| `{a}` | `{b}` | {what} | {label} | {s} | {p} | {wl} |")
            lines.append("")
    (OUT / f"generation_summary{suffix}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
