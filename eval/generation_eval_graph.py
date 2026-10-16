"""Experiment 3 addendum: does A*-graph evidence (R6d) change drafting and grounding?

Same protocol, prompt, metrics and 90 test requests as eval/generation_eval.py (R0/R1/R4/R5), plus condition R6d:
the model is shown the R6d evidence set (R5 seeds expanded by A* over the clause graph, 1,200-token budget), i.e. the
requested clauses together with the definitions, cross-referenced clauses and legally required clauses they depend on.
Writes eval/results/exp3/generation_r6d_per_item.jsonl and generation_r6d_summary.md (R4/R5 rows re-read from the
original run for comparison).

Usage:  python eval/generation_eval_graph.py [--seeds 1 2 3]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.generation_eval import PROMPT_RAG, SYSTEM, choose_items, parse, score  # noqa: E402
from eval.metrics.retrieval_metrics import bootstrap_ci  # noqa: E402
from src.common import ROOT, load_synthetic, read_jsonl  # noqa: E402
from src.llm.ollama import OllamaLLM  # noqa: E402
from src.retrieval.service import ClauseSearch  # noqa: E402

OUT = ROOT / "eval" / "results" / "exp3"
METRICS = ["citation_accuracy", "hallucinated_rate", "claim_support", "ask_recall", "context_clauses", "correct_abstention", "false_citation"]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="*", default=[1, 2, 3])
    args = ap.parse_args()
    ds = load_synthetic()
    clauses = ds.meta["clauses"]
    by_key_to_id = {c["key"]: cid for cid, c in clauses.items()}
    items = choose_items(ds, 90)
    search = ClauseSearch()
    llm = OllamaLLM(num_ctx=8192, cache_name="gen")
    rows = []
    for q in items:
        ev = search.evidence(q.text, budget=1200, n_seeds=5)
        shown = set(ev)
        block = "\n\n".join(f"[clause_id: {u}] {clauses[u]['title']}\n{clauses[u]['text']}" for u in ev)
        prompt = PROMPT_RAG.format(request=q.text, clauses=block)
        for seed in args.seeds:
            out = llm.generate(prompt, system=SYSTEM, temperature=0.3, seed=seed, json_mode=True, max_tokens=700)
            m = score(q, parse(out["text"]), clauses, by_key_to_id, shown)
            rows.append(dict(condition="R6d", qid=q.qid, seed=seed, latency_s=out["latency_s"], context_clauses=len(shown), **m, raw=out["text"][:4000]))
    with open(OUT / "generation_r6d_per_item.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    prior = [r for r in read_jsonl(OUT / "generation_per_item.jsonl") if r["condition"] in ("R4", "R5")]
    allrows = prior + rows
    lines = ["# Experiment 3 addendum: drafting with A*-graph evidence (R6d)", "",
             f"{len(items)} held-out requests, seeds {args.seeds}, qwen2.5:7b, same prompt and metrics as generation_summary.md. "
             "R4/R5 rows are the original run. Brackets: 95% bootstrap CIs over requests.", "",
             "| Condition | " + " | ".join(METRICS) + " |", "|---|" + "---|" * len(METRICS)]
    for cond in ("R4", "R5", "R6d"):
        cells = []
        for m in METRICS:
            per = []
            for q in items:
                vals = [r[m] for r in allrows if r["condition"] == cond and r["qid"] == q.qid and m in r and r[m] == r[m]]
                if vals:
                    per.append(float(np.mean(vals)))
            mean, lo, hi = bootstrap_ci(per) if per else (float("nan"),) * 3
            cells.append("–" if mean != mean else (f"{mean:.1f}" if m == "context_clauses" else f"{mean:.3f} [{lo:.3f}, {hi:.3f}]"))
        lines.append(f"| {cond} | " + " | ".join(cells) + " |")
    (OUT / "generation_r6d_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
