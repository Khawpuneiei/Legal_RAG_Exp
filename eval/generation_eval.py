"""Generation and grounding evaluation for Experiment 3 (docs/project-plan.md section 5.4, grounding metrics).

For a fixed 30-request subset of the synthetic test split, a local LLM (Ollama) is asked to pick an
approved clause for each requirement in the request and to quote the clause text that supports the
pick. Conditions differ only in what the model is shown:

  R0  nothing (no retrieval): the model must draft from its own knowledge
  R1  clauses covered by the top-5 naive fixed-size chunks
  R4  top-5 clauses from hybrid + reranker
  R5  top-5 clauses from R4 + contextual enrichment

Metrics (computed deterministically, no LLM judge):
  citation_accuracy     cited clause_id exists and is a gold clause for one of the request's asks
  hallucinated_rate     selections not traceable to the library (fabricated id, or drafted text with no id)
  claim_support         cited selections whose evidence quote (>= 8 words) appears verbatim in the cited clause
  ask_recall            share of the request's asks satisfied by a correct citation
  abstention            for requests containing an unsupported ask: the model left at least one requirement
                        unmatched (clause_id null) instead of forcing a citation

Usage:  python eval/generation_eval.py [--n 30] [--seeds 1 2 3]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import clause_catalog as cat  # noqa: E402
from eval.metrics.retrieval_metrics import bootstrap_ci  # noqa: E402
from src.common import ROOT, load_synthetic, read_jsonl  # noqa: E402
from src.llm.ollama import OllamaLLM  # noqa: E402

OUT = ROOT / "eval" / "results" / "exp3"
CONDITIONS = ["R0", "R1", "R4", "R5"]

SYSTEM = ("You are a legal drafting assistant at a Singapore fund management company regulated by the Monetary "
          "Authority of Singapore. Accuracy matters more than completeness.")
PROMPT_RAG = """Request from a colleague:
<request>
{request}
</request>

Approved clause library excerpts (the ONLY clauses you may use):
{clauses}

For each specific requirement or special term in the request (ignore routine drafting of the standard template), select the approved clause above that satisfies it.
Return JSON: {{"selections": [{{"requirement": "<short description>", "clause_id": "<clause_id from the excerpts, or null>", "evidence_quote": "<an exact quote of at least 8 consecutive words from the selected clause, or empty>"}}]}}
If none of the excerpts satisfies a requirement, set clause_id to null and evidence_quote to "". Never invent a clause_id."""
PROMPT_R0 = """Request from a colleague:
<request>
{request}
</request>

You do not have access to the firm's approved clause library. For each specific requirement or special term in the request (ignore routine drafting of the standard template), draft a suitable clause.
Return JSON: {{"selections": [{{"requirement": "<short description>", "clause_id": null, "evidence_quote": "<your drafted clause text>"}}]}}"""


def norm(s: str) -> str:
    s = s.lower().replace("’", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[^a-z0-9%.' ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip(" .")


def quote_supported(quote: str, clause_text: str) -> bool:
    q = norm(quote)
    return len(q.split()) >= 8 and q in norm(clause_text)


def ask_gold(agreement_type: str, ask: str, by_key_to_id: dict[str, str]) -> set[str]:
    g = cat.ASKS[ask]["gold"]
    return {by_key_to_id[k] for k, grade in (g.get(agreement_type) or g["*"]).items() if grade >= 2}


def choose_items(ds, n: int, seed: int = 7) -> list:
    test = [q for q in ds.queries if q.meta["split"] == "test"]
    rng = random.Random(seed)
    missing = [q for q in test if q.meta["missing_asks"]]
    rest = [q for q in test if not q.meta["missing_asks"]]
    k_missing = min(len(missing), max(5, n // 6))
    items = rng.sample(missing, k_missing) + rng.sample(rest, n - k_missing)
    return sorted(items, key=lambda q: q.qid)


def parse(text: str) -> list[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    sel = data.get("selections", []) if isinstance(data, dict) else []
    return [s for s in sel if isinstance(s, dict)]


def score(q, selections: list[dict], clauses: dict, by_key_to_id: dict, shown: set[str]) -> dict:
    gold_any = {cid for cid, g in q.graded.items() if g >= 2}
    cited = [s for s in selections if s.get("clause_id") not in (None, "", "null")]
    valid = [s for s in cited if s["clause_id"] in clauses]
    correct = [s for s in valid if s["clause_id"] in gold_any]
    supported = [s for s in valid if quote_supported(str(s.get("evidence_quote", "")), clauses[s["clause_id"]]["text"])]
    fabricated = [s for s in cited if s["clause_id"] not in clauses]
    uncited_drafts = [s for s in selections if s.get("clause_id") in (None, "", "null") and len(str(s.get("evidence_quote", "")).split()) >= 8]
    asks = q.meta["asks"]
    cited_ids = {s["clause_id"] for s in valid}
    satisfied = [a for a in asks if cited_ids & ask_gold(q.meta["agreement_type"], a, by_key_to_id)]
    m = dict(n_selections=len(selections), n_cited=len(cited),
             citation_accuracy=(len(correct) / len(cited)) if cited else float("nan"),
             hallucinated_rate=((len(fabricated) + len(uncited_drafts)) / len(selections)) if selections else float("nan"),
             claim_support=(len(supported) / len(valid)) if valid else float("nan"),
             ask_recall=(len(satisfied) / len(asks)) if asks else float("nan"),
             outside_context=(sum(1 for s in valid if s["clause_id"] not in shown) / len(valid)) if valid and shown else float("nan"))
    if q.meta["missing_asks"]:
        m["abstention"] = 1.0 if any(s.get("clause_id") in (None, "", "null") for s in selections) else 0.0
    return m


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seeds", type=int, nargs="*", default=[1, 2, 3])
    ap.add_argument("--temperature", type=float, default=0.3)
    args = ap.parse_args()
    ds = load_synthetic()
    clauses = ds.meta["clauses"]
    by_key_to_id = {c["key"]: cid for cid, c in clauses.items()}
    rankings = {(r["condition"], r["qid"]): r for r in read_jsonl(OUT / "rankings.jsonl") if r["dataset"] == "synthetic"}
    items = choose_items(ds, args.n)
    llm = OllamaLLM(num_ctx=8192, cache_name="gen")
    rows = []
    for cond in CONDITIONS:
        for q in items:
            if cond == "R0":
                shown, prompt = set(), PROMPT_R0.format(request=q.text)
            else:
                units = rankings[(cond, q.qid)]["unit_ids"]
                if cond == "R1":
                    # all clauses covered by the top-5 fixed chunks (naive RAG passes whole windows)
                    from src.retrieval.chunking import fixed_chunks
                    from eval.metrics.retrieval_metrics import chunk_units
                    if not hasattr(main, "_r1"):
                        ch = fixed_chunks(ds)
                        main._r1 = (ch, chunk_units(ds, ch))
                    ch, cov = main._r1
                    idx = {c.chunk_id: i for i, c in enumerate(ch)}
                    shown_list = []
                    for cid in rankings[(cond, q.qid)]["chunk_ids"][:5]:
                        for u in cov[idx[cid]]:
                            if u not in shown_list:
                                shown_list.append(u)
                else:
                    shown_list = units[:5]
                shown = set(shown_list)
                block = "\n\n".join(f"[clause_id: {u}] {clauses[u]['title']}\n{clauses[u]['text']}" for u in shown_list)
                prompt = PROMPT_RAG.format(request=q.text, clauses=block)
            for seed in args.seeds:
                out = llm.generate(prompt, system=SYSTEM, temperature=args.temperature, seed=seed, json_mode=True, max_tokens=700)
                sel = parse(out["text"])
                m = score(q, sel, clauses, by_key_to_id, shown)
                rows.append(dict(condition=cond, qid=q.qid, seed=seed, latency_s=out["latency_s"], context_clauses=len(shown), **m,
                                 raw=out["text"][:4000]))
            print(f"  {cond} {q.qid} done")
    llm.unload()
    with open(OUT / "generation_per_item.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    metrics = ["citation_accuracy", "hallucinated_rate", "claim_support", "ask_recall", "abstention", "n_selections", "context_clauses", "latency_s"]
    lines = ["# Experiment 3: generation and grounding (synthetic test subset)", "",
             f"{len(items)} requests from the held-out test split (seeded sample, {sum(1 for q in items if q.meta['missing_asks'])} contain an ask the library cannot satisfy), "
             f"{len(args.seeds)} seeds each, temperature {args.temperature}, model {llm.model} via Ollama. Per-request means are averaged over seeds, then over requests; brackets are 95% bootstrap CIs over requests.", "",
             "| Condition | " + " | ".join(metrics) + " |", "|---|" + "---|" * len(metrics)]
    summary = []
    for cond in CONDITIONS:
        cells = []
        for m in metrics:
            per_item = []
            for q in items:
                vals = [r[m] for r in rows if r["condition"] == cond and r["qid"] == q.qid and m in r and not (isinstance(r[m], float) and np.isnan(r[m]))]
                if vals:
                    per_item.append(float(np.mean(vals)))
            mean, lo, hi = bootstrap_ci(per_item) if per_item else (float("nan"),) * 3
            summary.append(dict(condition=cond, metric=m, mean=mean, ci_low=lo, ci_high=hi, n=len(per_item)))
            if np.isnan(mean):
                cells.append("–")
            elif m in ("n_selections", "context_clauses", "latency_s"):
                cells.append(f"{mean:.1f}")
            else:
                cells.append(f"{mean:.3f} [{lo:.3f}, {hi:.3f}]")
        lines.append(f"| {cond} | " + " | ".join(cells) + " |")
    lines += ["", "Metric definitions are in the docstring of `eval/generation_eval.py`. R0 has no library, so its citation metrics are undefined and every drafted clause counts as not traceable to the library."]
    (OUT / "generation_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "generation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
