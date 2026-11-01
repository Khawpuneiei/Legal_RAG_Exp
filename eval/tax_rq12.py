"""RQ1 (a SKILL.md playbook) and RQ2 (harnesses, Deep Tax Research) on the teammate's tax RAG, answered by qwen3:8b.

Protocol: docs/taxrag-rq12-protocol.md. Every condition ends in his answer call (rag.generate: SYSTEM_PROMPT,
build_prompt over numbered sources, render_citations, an uncited answer becomes the refusal) with his 2,000-token cap,
thinking included; a condition changes the evidence (B1, DTR, DTRa), the prompt (S1-S4) or retries the call (V).
Helper calls (skill routing, planning, gap check, agent steps) run with thinking off, JSON out, at most 400 tokens.
Answers and helper replies are cached, Gemini query vectors too, so a rerun or a resumed run is cheap; a Gemini
embedding quota stops the run and keeps what is done.

    python eval/tax_rq12.py run --split dev --conditions B0 B1   # -> eval/results/tax/generation_per_question_rq12.jsonl
    python eval/tax_rq12.py run --split test                      # every condition (C once rq12_choice.json exists)
    python eval/tax_rq12.py self-skill                            # S4: qwen3:8b writes skills/tax-answering-self/SKILL.md
    python eval/tax_rq12.py summary                               # -> generation_summary_rq12.md
    python eval/tax_rq12.py choose                                # the protocol's dev choice of C -> rq12_choice.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.tax_experiment import OUT, Runner, load_keys  # noqa: E402
from eval.tax_generation import merge  # noqa: E402
from eval.tax_report import _fmt_diff, paired  # noqa: E402
from src.common import CACHE, read_jsonl  # noqa: E402
from src.llm.ollama import OllamaLLM  # noqa: E402
from src.tax import research as rs  # noqa: E402
from src.tax import skill as sk  # noqa: E402
from src.tax.corpus import chunks, tax_rag  # noqa: E402
from src.tax.graph import TaxGraph  # noqa: E402

MODEL = "qwen3:8b"
NUM_CTX = 16384          # one slot: every layer on the 8 GB GPU, and room for the comprehensive skill
ANSWER_TOKENS = 2000     # his rag.llm.MAX_ANSWER_TOKENS, thinking included
HELPER_TOKENS = 400
CANDIDATES = 50          # his rag.retrieve.CANDIDATES: the ranking a search query contributes to the merge
WIDE_BUDGET = 4000       # B0w: his `improved` with more context, a control added after the dev retrieval check
SEED = "structured_routed@gemini"
SUFFIX = "_rq12"
ROWS = OUT / f"generation_per_question{SUFFIX}.jsonl"
ANSWERS = CACHE / "tax" / f"generation_answers{SUFFIX}.jsonl"   # answer texts paraphrase IRAS guides: not in the repo
CHOICE = OUT / "rq12_choice.json"   # the dev choice of C: {"evidence", "skill", "validate"}
# name -> (evidence step, skill variant or None, validation retry)
CONDITIONS = {
    "B0": ("B0", None, False), "B1": ("B1", None, False), "B0w": ("B0w", None, False),
    "S1": ("B0", "S1", False), "S2": ("B0", "S2", False), "S3": ("B0", "S3", False), "S4": ("B0", "S4", False),
    "V": ("B0", None, True),
    "DTR": ("DTR", None, False), "DTR+V": ("DTR", None, True),
    "DTRa": ("DTRa", None, False), "DTRa+V": ("DTRa", None, True),
}
if CHOICE.exists():
    _c = json.loads(CHOICE.read_text(encoding="utf-8"))
    CONDITIONS["C"] = (_c["evidence"], _c["skill"], bool(_c["validate"]))
# (A, B, question): paired over a split's answerable questions
COMPARISONS = [
    ("S2", "B0", "RQ1: focused skill vs his prompt"),
    ("S1", "B0", "RQ1: whole skill in the system prompt vs his prompt"),
    ("S3", "B0", "RQ1: comprehensive skill vs his prompt"),
    ("S4", "B0", "RQ1: skill written by the model itself vs his prompt"),
    ("S2", "S3", "RQ1: focused vs comprehensive skill"),
    ("V", "B0", "RQ2: validation retry vs his single call"),
    ("DTR", "B0", "RQ2: Deep Tax Research vs his deployed context"),
    ("DTR", "B1", "RQ2: Deep Tax Research vs R6y alone"),
    ("B1", "B0", "R6y vs his deployed context (this round)"),
    ("B0w", "B0", "control: his retrieval with 4,000 tokens instead of 2,500"),
    ("DTR", "B0w", "Deep Tax Research vs simply more of his own ranking"),
    ("DTRa", "DTR", "RQ2: research agent vs fixed research pipeline"),
    ("DTR+V", "DTR", "RQ2: validation retry on Deep Tax Research"),
    ("DTRa+V", "DTRa", "RQ2: validation retry on the research agent"),
    ("C", "B0", "the combination chosen on dev vs his deployed setup"),
]
PRIMARY = [("S2", "B0"), ("V", "B0"), ("DTR", "B0")]   # the protocol's three primary comparisons (Holm-adjusted)
SETS = [("heldout", "test", "Held-out test split"), ("heldout", "dev", "Held-out dev split")]
SELF_PROMPT = ("Write a SKILL.md file (Anthropic Agent Skills format: YAML front matter with `name` and `description`, then Markdown "
               "instructions) that teaches an AI assistant to do this task well:\n\n"
               "Tax associates at accounting firms in Singapore ask questions about Singapore corporate income tax. The assistant "
               "receives a question and numbered sources retrieved from the Income Tax Act 1947 and the IRAS e-Tax guides, and must "
               "answer from those sources only, following this system prompt:\n\n{system}\n\n"
               "The questions cover five areas: group relief; loss carry-back; the start of a business; renovation, deductions and "
               "capital allowances; and the general Act.\n\nWrite practical, specific instructions. Output only the SKILL.md content.")


class PatientQueries:
    """His GeminiEmbedder for an unattended run: new queries go through its batch path, which waits and retries on
    5xx, dropped connections and per-minute limits and raises QuotaExhausted only on the daily quota, instead of the
    app's fail-fast query path. Same model, task type and normalisation, so the cached vectors stay valid."""

    def __init__(self, inner):
        self.inner, self.name = inner, inner.name

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.inner.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self.inner._embed_batch([text], "RETRIEVAL_QUERY")[0]


class Setup:
    """His retrieval on his Gemini index (exact search), the dependency graph and the two model clients."""

    def __init__(self):
        load_keys()
        self.runner = Runner()
        self.rag = self.runner.rag
        self.gen = self.rag.generate
        self.gem = self.runner.search("gemini", False)
        self.gem.query_embedder.inner = PatientQueries(self.gem.query_embedder.inner)
        self.graph = TaxGraph(chunks("structured"), self.gem.doc_vectors, self.rag.chunk.count_tokens)
        tuning = json.loads((OUT / "graph_tuning.json").read_text(encoding="utf-8"))
        self.r6y = tuning[SEED]["expand_dep"]   # allowance 450, lam = mu = 0
        # the answer cache and keys of `tax_generation.py --model qwen3:8b --num-ctx 16384`
        self.answer_llm = OllamaLLM(MODEL, num_ctx=NUM_CTX, cache_name="tax-answers")
        self.helper_llm = OllamaLLM(MODEL, num_ctx=NUM_CTX, cache_name="tax-helpers")
        self.skill = sk.read_skill() if (sk.SKILLS / sk.TAX_SKILL / "SKILL.md").exists() else None
        self.self_skill = sk.read_skill(sk.SELF_SKILL) if (sk.SKILLS / sk.SELF_SKILL / "SKILL.md").exists() else None

    def kit(self, q) -> rs.Kit:
        qvec = self.gem.query_embedder.embed_query(q.question)   # cached; with lam = mu = 0 it does not change A*
        lam, mu = self.r6y["best"]["lam"], self.r6y["best"]["mu"]

        def search(query: str) -> list:
            return [h.chunk for h in self.gem.retriever.search(query, "improved", CANDIDATES).hits]

        def expand(pinned: list, allowance: int, present: list = ()) -> list:
            added = self.graph.expand([c.chunk_id for c in pinned], qvec, allowance, lam, mu, follow_seed_only=False,
                                      present=[c.chunk_id for c in present])
            return [self.graph.chunks[c] for c in added]

        return rs.Kit(search, expand, self.rag.chunk.count_tokens, self.gen.format_source, self.runner.budget, self.r6y["allowance"])

    def evidence(self, step: str, q, kit: rs.Kit, helper, trace: rs.Trace) -> list:
        result = self.gem.retriever.search(q.question, "improved", budget=self.runner.budget)
        hits = [h.chunk for h in result.hits]
        if step == "B0w":
            wide = self.gem.retriever.search(q.question, "improved", budget=WIDE_BUDGET)
            return [h.chunk for h in wide.hits] + wide.expanded
        if step == "B0":
            return hits + result.expanded           # his app: hits plus his one-hop expansion
        if step == "B1":
            return rs.follow_references(hits, kit)  # R6y
        if step == "DTR":
            return rs.deep_tax_research(q.question, kit, helper, trace)
        if step == "DTRa":
            return rs.research_agent(q.question, kit, helper, trace)
        raise ValueError(step)

    def prompts(self, variant: str | None, q, sources: list, helper) -> tuple[str, str, list | None]:
        """(system, user, loaded modules): his prompt, with the skill placed as in the legal S1-S4."""
        user = self.gen.build_prompt(q.question, sources)
        if variant is None:
            return self.gen.SYSTEM_PROMPT, user, None
        if variant == "S1":
            return self.gen.SYSTEM_PROMPT + "\n\n# Answering instructions\n\n" + sk.comprehensive_text(self.skill), user, None
        if variant == "S2":
            reply = rs.parse_json(helper(sk.route_prompt(self.skill, q.question)).get("text", ""))
            chosen = sk.chosen_modules(self.skill, reply)
            block = sk.skill_block(self.skill["name"], self.skill["body"], {p: self.skill["modules"][p] for p in chosen})
            return self.gen.SYSTEM_PROMPT, f"{sk.LOADED}\n\n{block}\n\n{user}", chosen
        if variant == "S3":
            block = sk.skill_block(self.skill["name"] + "-comprehensive", sk.comprehensive_text(self.skill), {})
        elif variant == "S4":
            block = sk.skill_block(self.self_skill["name"], self.self_skill["body"], {})
        else:
            raise ValueError(variant)
        return self.gen.SYSTEM_PROMPT, f"{sk.LOADED}\n\n{block}\n\n{user}", None

    def run(self, condition: str, q) -> tuple[dict, dict]:
        step, variant, validate = CONDITIONS[condition]
        calls: list[dict] = []

        def record(kind: str, out: dict) -> dict:
            calls.append(dict(kind=kind, **{k: out.get(k) for k in ("latency_s", "compute_s", "prompt_tokens", "completion_tokens",
                                                                    "cached", "done_reason")}))
            return out

        def helper(prompt: str) -> dict:
            return record("helper", self.helper_llm.generate(prompt, json_mode=True, max_tokens=HELPER_TOKENS, think=False))

        def answer(system: str, user: str) -> dict:
            return record("answer", self.answer_llm.generate(user, system=system, max_tokens=ANSWER_TOKENS))

        trace, kit = rs.Trace(), self.kit(q)
        sources = self.evidence(step, q, kit, helper, trace)
        system, user, loaded = self.prompts(variant, q, sources, helper)

        def render(raw: str):
            return self.gen.render_citations(raw, sources)

        if not sources:
            raw, attempts = "", []
        elif validate:
            reply, attempts = rs.answer_with_retry(answer, render, system, user, len(sources), self.gen.REFUSAL)
            raw = reply.get("text", "")
        else:
            reply = answer(system, user)
            raw = reply.get("text", "")
            _, cited, invalid = render(raw)
            attempts = [dict(raw=raw, done_reason=reply.get("done_reason"),
                             problems=rs.problems(raw, reply.get("done_reason"), cited, invalid, self.gen.REFUSAL))]
        text, cited, invalid = render(raw) if sources else ("", [], [])
        refused = not cited
        rag, sp = self.rag, self.runner.sp
        units = lambda cs: set().union(*(rag.evaluate.units_hit(c, q.gold_units, sp) for c in cs)) if cs else set()  # noqa: E731
        answers = [c for c in calls if c["kind"] == "answer"]
        row = dict(qset=q.qset, split=q.split, qid=q.id, type=q.type, answerable=q.answerable, condition=condition,
                   refused=refused, model_called=bool(answers), n_sources=len(sources),
                   source_tokens=sum(rag.chunk.count_tokens(c.text) for c in sources), n_cited=len(cited),
                   invalid_citations=len(invalid),
                   citation_precision=rag.evaluate.citation_precision(cited, q.gold_units, sp) if q.answerable and cited else None,
                   gold_cited=len(units(cited)) / len(q.gold_units) if q.answerable else None,
                   gold_in_context=len(units(sources)) / len(q.gold_units) if q.answerable else None,
                   cited=[c.chunk_id for c in cited], answer_calls=len(answers), helper_calls=len(calls) - len(answers),
                   retries=max(0, len(answers) - 1), searches=max(0, len(trace.queries) - 1),
                   prompt_tokens=sum(c["prompt_tokens"] or 0 for c in calls),
                   completion_tokens=sum(c["completion_tokens"] or 0 for c in calls),
                   # the model's own compute time where recorded (queueing behind other clients excluded)
                   seconds=round(sum((c["compute_s"] if c.get("compute_s") is not None else c["latency_s"]) or 0 for c in calls), 1),
                   cap_hits=sum(c["done_reason"] == "length" for c in answers),
                   empty_replies=sum(not a["raw"].strip() for a in attempts),
                   final_problems=attempts[-1]["problems"] if attempts else [],
                   declined=raw.strip() == self.gen.REFUSAL, loaded_modules=loaded)
        rec = dict(qset=q.qset, qid=q.id, condition=condition, text=self.gen.REFUSAL if refused else text, raw=raw,
                   sources=[c.chunk_id for c in sources], attempts=attempts, trace=trace.steps, queries=trace.queries)
        return row, rec


def run(args) -> None:
    s = Setup()
    conds = args.conditions or list(CONDITIONS)
    unknown = [c for c in conds if c not in CONDITIONS]
    if unknown:
        raise SystemExit(f"unknown conditions {unknown}; known: {list(CONDITIONS)}")
    if any(CONDITIONS[c][1] in ("S1", "S2", "S3") for c in conds) and s.skill is None:
        raise SystemExit("skills/tax-answering/SKILL.md is not written yet")
    if any(CONDITIONS[c][1] == "S4" for c in conds) and s.self_skill is None:
        raise SystemExit("run `python eval/tax_rq12.py self-skill` first")
    qs = [q for q in s.runner.questions if q.qset == "heldout" and q.split == args.split]
    if args.limit:
        qs = qs[:args.limit]
    jobs = [(c, q) for q in qs for c in conds]   # question by question, so a partial run is still paired
    stop_errors = (s.rag.embed.QuotaExhausted, *s.rag.llm.PROVIDER_ERRORS)
    rows, recs = [], []

    def save() -> None:
        done = {(r["condition"], r["qset"], r["qid"]) for r in rows}
        merge(ROWS, rows, done)
        merge(ANSWERS, recs, done)

    for i, (c, q) in enumerate(jobs, start=1):
        try:
            row, rec = s.run(c, q)
        except stop_errors as error:   # the Gemini embedding quota or an outage: keep what is done, resume later
            print(f"stopped at {c} {q.id}: {type(error).__name__}: {error}", flush=True)
            save()
            summary()
            sys.exit(1)
        rows.append(row)
        recs.append(rec)
        print(f"{i}/{len(jobs)} {c} {q.id}: {row['answer_calls']}+{row['helper_calls']} calls, {row['seconds']:.0f}s, "
              f"{'refused' if row['refused'] else 'answered'}{' cap' if row['cap_hits'] else ''}", flush=True)
        if i % 20 == 0:
            save()
    save()
    summary()


def self_skill() -> None:
    """S4: qwen3:8b writes its own skill from the task description, his system prompt and the five areas (no corpus text)."""
    path = sk.SKILLS / sk.SELF_SKILL / "SKILL.md"
    if path.exists():
        print(f"{path} exists; delete it to write a new one")
        return
    gen = tax_rag().generate
    llm = OllamaLLM(MODEL, num_ctx=NUM_CTX, cache_name="tax-skill")
    out = llm.generate(SELF_PROMPT.format(system=gen.SYSTEM_PROMPT), system="You are an expert at writing instructions for AI agents.",
                       temperature=0.7, seed=0, max_tokens=6000)
    text = out["text"].strip()
    if not text:
        raise SystemExit(f"no text (done_reason {out.get('done_reason')}); the reasoning used the whole budget")
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    if not text.lstrip().startswith("---"):
        text = f"---\nname: {sk.SELF_SKILL}\ndescription: Self-generated skill (TaxRAG RQ1, condition S4).\n---\n\n" + text
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(text.split())} words, done_reason {out.get('done_reason')}, {out.get('completion_tokens')} tokens)")


def summary() -> None:
    rows = read_jsonl(ROWS) if ROWS.exists() else []
    for r in rows:
        if r["answerable"]:
            r["answered"] = float(not r["refused"])
            r["gold_cited_all"] = 0.0 if r["refused"] else r["gold_cited"]
    lines = ["# TaxRAG RQ1 and RQ2 (qwen3:8b): answers per condition", "",
             "Protocol: docs/taxrag-rq12-protocol.md. Gold cited (all): share of the question's gold units the answer cites, a "
             "refusal counting 0. Gold in context: share of the gold units the sources contain. Calls: answer + helper calls per "
             "question. Model tokens: prompt + completion tokens of those calls per question, thinking included. Seconds: model "
             "time per question. Cap: answer calls that stopped at the 2,000-token cap.", ""]
    for qset, split, title in SETS:
        sub = [r for r in rows if r["qset"] == qset and r["split"] == split]
        if not sub:
            continue
        lines += [f"## {title}", "", "| Condition | Answerable answered | Out-of-scope refused | Citation precision | Gold cited (all) | "
                  "Gold in context | Source tokens | Calls | Model tokens | Seconds | Cap | Retries |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for c in [c for c in CONDITIONS if any(r["condition"] == c for r in sub)]:
            rs_ = [r for r in sub if r["condition"] == c]
            ans = [r for r in rs_ if r["answerable"]]
            oos = [r for r in rs_ if not r["answerable"]]
            prec = [r["citation_precision"] for r in ans if r["citation_precision"] is not None]
            lines.append(f"| `{c}` | {int(sum(r['answered'] for r in ans))}/{len(ans)} | {sum(r['refused'] for r in oos)}/{len(oos)} | "
                         f"{np.mean(prec) if prec else float('nan'):.3f} | {np.mean([r['gold_cited_all'] for r in ans]):.3f} | "
                         f"{np.mean([r['gold_in_context'] for r in ans]):.3f} | {np.mean([r['source_tokens'] for r in rs_]):.0f} | "
                         f"{np.mean([r['answer_calls'] + r['helper_calls'] for r in rs_]):.1f} | "
                         f"{np.mean([r['prompt_tokens'] + r['completion_tokens'] for r in rs_]):,.0f} | {np.mean([r['seconds'] for r in rs_]):.0f} | "
                         f"{sum(r['cap_hits'] for r in rs_)} | {sum(r['retries'] for r in rs_)} |")
        lines.append("")
        answerable = [r for r in sub if r["answerable"]]
        present = {r["condition"] for r in answerable}
        comps = [(a, b, w) for a, b, w in COMPARISONS if a in present and b in present]
        if comps:
            lines += ["Paired over the answerable questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A better / worse. "
                      "**Bold**: the CI excludes 0.", "",
                      "| A | B | Question | Metric | Mean A − B [95% CI] | Wilcoxon p | A better / worse |", "|---|---|---|---|---|---|---|"]
            for a, b, what in comps:
                for m, label in [("gold_cited_all", "gold cited (all)"), ("answered", "answered"), ("gold_in_context", "gold in context")]:
                    s_, p, wl = _fmt_diff(paired(answerable, a, b, m))
                    lines.append(f"| `{a}` | `{b}` | {what} | {label} | {s_} | {p} | {wl} |")
            lines.append("")
    (OUT / f"generation_summary{SUFFIX}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def choose() -> None:
    """The protocol's dev choice of C, from the dev judging (judge_per_question_rq12-dev.jsonl): the skill (none, S1-S4)
    and the evidence step (B0, B1, DTR, DTRa) with the highest dev correct (all), the shorter prompt or the fewer calls
    within 0.01 of the best, and the retry if V scores at least as high as B0. Writes rq12_choice.json."""
    judged = read_jsonl(OUT / f"judge_per_question{SUFFIX}-dev.jsonl")
    gen = [r for r in read_jsonl(ROWS) if r["split"] == "dev" and r["answerable"]]
    correct = {c: float(np.mean([r["correct_all"] for r in judged if r["condition"] == c])) for c in {r["condition"] for r in judged}}
    prompt = {c: float(np.mean([r["prompt_tokens"] for r in gen if r["condition"] == c])) for c in correct}
    calls = {c: float(np.mean([r["answer_calls"] + r["helper_calls"] for r in gen if r["condition"] == c])) for c in correct}

    def best(options: list[str], cost: dict) -> str:
        top = max(correct[c] for c in options)
        return min((c for c in options if correct[c] >= top - 0.01), key=lambda c: (cost[c], options.index(c)))

    skill = best(["B0", "S1", "S2", "S3", "S4"], prompt)
    evidence = best(["B0", "B1", "DTR", "DTRa"], calls)
    choice = dict(skill=None if skill == "B0" else skill, evidence=evidence, validate=correct["V"] >= correct["B0"],
                  dev_correct_all={c: round(v, 4) for c, v in sorted(correct.items())},
                  dev_prompt_tokens={c: round(v) for c, v in sorted(prompt.items())},
                  dev_calls={c: round(v, 2) for c, v in sorted(calls.items())})
    CHOICE.write_text(json.dumps(choice, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(choice, indent=1))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--split", choices=["test", "dev"], default="dev")
    r.add_argument("--conditions", nargs="*", default=None)
    r.add_argument("--limit", type=int, default=None, help="only the first N questions (pilots)")
    sub.add_parser("self-skill")
    sub.add_parser("summary")
    sub.add_parser("choose", help="the dev choice of C -> eval/results/tax/rq12_choice.json")
    args = ap.parse_args()
    if args.cmd == "run":
        run(args)
    elif args.cmd == "self-skill":
        self_skill()
    elif args.cmd == "choose":
        choose()
    else:
        summary()


if __name__ == "__main__":
    main()
