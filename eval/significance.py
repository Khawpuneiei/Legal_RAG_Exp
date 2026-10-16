"""Paired comparisons for the Experiment 3 write-up (plan section 7: paired tests + bootstrap CIs).

For each comparison A vs B on the same queries: mean difference (A - B) with a 95% paired bootstrap CI,
and a two-sided Wilcoxon signed-rank p-value (zero differences dropped). LegalBench-RAG differences are
weighted so its four sources count equally, as in the official script; the Wilcoxon test is unweighted.
Usage:  python eval/significance.py   -> eval/results/exp3/significance.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import ROOT, read_jsonl  # noqa: E402

RES = ROOT / "eval" / "results" / "exp3"
COMPARISONS = [
    ("synthetic", "ndcg@10", "R3", "R2", "Adding BM25 (hybrid) to dense clause retrieval"),
    ("synthetic", "ndcg@10", "R4", "R1", "Full pipeline (R4) vs naive RAG"),
    ("synthetic", "ndcg@10", "R4", "R3", "Adding the cross-encoder reranker"),
    ("synthetic", "ndcg@10", "R4e", "R4", "Qwen3-Embedding-0.6B vs BGE-M3"),
    ("synthetic", "ndcg@10", "R4q", "R4", "Doctrinal query rewrite"),
    ("synthetic", "ndcg@10", "R5", "R4", "Contextual chunk enrichment"),
    ("synthetic", "recall@5", "R5", "R4", "Contextual chunk enrichment (Recall@5)"),
    ("acord-test", "ndcg@10", "R4", "R1", "Full pipeline vs naive RAG"),
    ("acord-test", "ndcg@10", "R4", "R3", "Adding the reranker"),
    ("acord-test", "ndcg@10", "R4e", "R4", "Qwen3-Embedding-0.6B vs BGE-M3"),
    ("acord-test", "ndcg@10", "R4q", "R4", "Doctrinal query rewrite"),
    ("lbr-mini", "char_r@8kchars", "R1", "R2", "Fixed 2,000-char vs 500-char chunks (equal budget)"),
    ("lbr-mini", "char_r@8kchars", "R3", "R2", "Adding BM25 (hybrid)"),
    ("lbr-mini", "char_r@8kchars", "R4", "R3", "Adding the reranker"),
    ("lbr-mini", "char_r@8kchars", "R4e", "R4", "Qwen3-Embedding-0.6B vs BGE-M3"),
    ("lbr-mini", "char_r@8kchars", "R4q", "R4", "Doctrinal query rewrite"),
    ("lbr-mini", "char_r@8kchars", "R5", "R4", "SAC document summaries"),
    ("lbr-mini", "char_p@1", "R5", "R4", "SAC document summaries (precision@1)"),
    ("synthetic-graph", "definition_coverage", "R6c", "R5@budget", "A* expansion vs flat R5, same budget"),
    ("synthetic-graph", "clause_recall", "R6c", "R5@budget", "A* expansion vs flat R5, same budget"),
    ("synthetic-graph", "definition_coverage", "R6c", "R6a", "A* vs BFS"),
    ("synthetic-graph", "xref_completeness", "R6c", "R6a", "A* vs BFS"),
    ("synthetic-graph", "clause_recall", "R6c", "R6a", "A* vs BFS"),
    ("synthetic-graph", "requires_satisfied", "R6c", "R6a", "A* vs BFS"),
    ("synthetic-graph", "xref_completeness", "R6d", "R6c", "Tuned vs admissible heuristic"),
]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = read_jsonl(RES / "per_query.jsonl")
    idx = {}
    for r in rows:
        if r["dataset"].startswith("synthetic") and r["split"] != "test":
            continue
        idx[(r["dataset"], r["condition"], r["qid"])] = r
    lines = ["# Experiment 3: paired comparisons", "",
             "A − B on the same queries (synthetic: 90-request test split). 95% paired bootstrap CI (2,000 resamples); "
             "two-sided Wilcoxon signed-rank p-value. Differences whose CI excludes 0 are marked **bold**.", "",
             "| Dataset | Metric | A | B | What changes | Mean A − B [95% CI] | Wilcoxon p | n |", "|---|---|---|---|---|---|---|---|"]
    rng = np.random.default_rng(0)
    for ds, metric, a, b, label in COMPARISONS:
        qids = sorted({q for (d, c, q) in idx if d == ds and c == a} & {q for (d, c, q) in idx if d == ds and c == b})
        pairs = [(idx[(ds, a, q)].get(metric), idx[(ds, b, q)].get(metric), idx[(ds, a, q)].get("weight", 1.0)) for q in qids]
        pairs = [(x, y, w) for x, y, w in pairs if x is not None and y is not None and not (np.isnan(x) or np.isnan(y))]
        if not pairs:
            continue
        d = np.array([x - y for x, y, _ in pairs])
        w = np.array([wt for _, _, wt in pairs])
        mean = float(np.sum(d * w) / np.sum(w))
        bi = rng.integers(0, len(d), size=(2000, len(d)))
        boots = np.sum(d[bi] * w[bi], axis=1) / np.sum(w[bi], axis=1)
        lo, hi = np.percentile(boots, [2.5, 97.5])
        nz = d[d != 0]
        p = wilcoxon(nz).pvalue if len(nz) >= 10 else float("nan")
        cell = f"{mean:+.3f} [{lo:+.3f}, {hi:+.3f}]"
        if lo > 0 or hi < 0:
            cell = f"**{cell}**"
        ptxt = "–" if np.isnan(p) else (f"{p:.1e}" if p < 0.001 else f"{p:.3f}")
        lines.append(f"| {ds} | {metric} | {a} | {b} | {label} | {cell} | {ptxt} | {len(d)} |")
    # Generation / grounding: per-request means over seeds, paired across conditions
    gen_path = RES / "generation_per_item.jsonl"
    if gen_path.exists():
        g = read_jsonl(gen_path)
        per = {}
        for r in g:
            per.setdefault((r["condition"], r["qid"]), []).append(r)
        lines += ["", "## Generation and grounding (30 test requests, means over 3 seeds per request)", "",
                  "| Metric | A | B | Mean A − B [95% CI] | Wilcoxon p | n |", "|---|---|---|---|---|---|"]
        for metric, a, b in [("citation_accuracy", "R4", "R1"), ("ask_recall", "R4", "R1"), ("hallucinated_rate", "R4", "R1"),
                             ("ask_recall", "R5", "R4"), ("citation_accuracy", "R5", "R4"), ("hallucinated_rate", "R1", "R0")]:
            d = []
            for (c, q), rs in per.items():
                if c != a or (b, q) not in per:
                    continue
                va = [r[metric] for r in rs if not np.isnan(r.get(metric, np.nan))]
                vb = [r[metric] for r in per[(b, q)] if not np.isnan(r.get(metric, np.nan))]
                if va and vb:
                    d.append(float(np.mean(va) - np.mean(vb)))
            if not d:
                continue
            d = np.array(d)
            boots = d[rng.integers(0, len(d), size=(2000, len(d)))].mean(axis=1)
            lo, hi = np.percentile(boots, [2.5, 97.5])
            nz = d[d != 0]
            p = wilcoxon(nz).pvalue if len(nz) >= 10 else float("nan")
            cell = f"{d.mean():+.3f} [{lo:+.3f}, {hi:+.3f}]"
            if lo > 0 or hi < 0:
                cell = f"**{cell}**"
            ptxt = "–" if np.isnan(p) else (f"{p:.1e}" if p < 0.001 else f"{p:.3f}")
            lines.append(f"| {metric} | {a} | {b} | {cell} | {ptxt} | {len(d)} |")
    (RES / "significance.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
