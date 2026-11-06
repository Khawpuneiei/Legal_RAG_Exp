"""Write-up tables, paired tests and figures for the TaxRAG experiment (eval/tax_experiment.py report)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon

from src.common import read_jsonl

# The teammate's published rows (results/metrics.md at commit ac04f49, Gemini gemini-embedding-001 for dense):
# Recall@5, MRR@10, Recall @ 2,500 tokens on his 25 answerable questions.
PUBLISHED = {
    "naive_bm25": (0.44, 0.46, 0.44), "naive_dense": (0.67, 0.62, 0.67), "structured_bm25": (0.42, 0.43, 0.59),
    "structured_bm25_boost": (0.42, 0.42, 0.59), "structured_dense": (0.63, 0.81, 0.80), "structured_hybrid": (0.59, 0.64, 0.78),
    "structured_hybrid_boost": (0.59, 0.63, 0.78), "structured_routed": (0.71, 0.80, 0.81),
}
FLAT_ORDER = ["naive_bm25", "structured_bm25", "structured_bm25_boost", "naive_dense@bge-m3", "structured_dense@bge-m3",
              "structured_hybrid@bge-m3", "structured_hybrid_boost@bge-m3", "structured_routed@bge-m3",
              "R4", "R4f", "R4-routed", "R4-bm25", "R4e", "R5", "R5f", "D1", "D2", "D1i",
              "naive_dense@gemini", "structured_dense@gemini", "structured_hybrid@gemini", "structured_hybrid_boost@gemini",
              "structured_routed@gemini", "R4@gemini", "R4f@gemini", "R4-routed@gemini", "D3@gemini", "D3i@gemini"]
LABEL = {
    "naive_bm25": "naive chunks, BM25", "structured_bm25": "structured, BM25", "structured_bm25_boost": "structured, BM25 + section boost",
    "naive_dense@bge-m3": "naive chunks, dense (his `baseline`)", "structured_dense@bge-m3": "structured, dense",
    "structured_hybrid@bge-m3": "structured, BM25 + dense", "structured_hybrid_boost@bge-m3": "structured, BM25 + dense + boost",
    "structured_routed@bge-m3": "structured, routed (his `improved`)",
    "R4": "R4: hybrid + boost, then reranker", "R4-routed": "R4 on the routed first stage", "R4-bm25": "R4 on BM25 + boost only",
    "R4e": "R4 with Qwen3-Embedding-0.6B", "R5": "R5: R4 + contextual chunks",
    "R4f": "R4, reranker rank fused with first stage (RRF)", "R5f": "R5, reranker rank fused with first stage (RRF)",
    "D1": "D1 (CPU): BM25 + boost, MiniLM reranker",
    "D1i": "D1i (CPU, as shipped): BM25 + boost, int8 ONNX MiniLM, top 20, fused", "D2": "D2 (CPU): bge-small hybrid, MiniLM reranker",
    "naive_dense@gemini": "naive chunks, Gemini dense (his `baseline`)", "structured_dense@gemini": "structured, Gemini dense",
    "structured_hybrid@gemini": "structured, BM25 + Gemini", "structured_hybrid_boost@gemini": "structured, BM25 + Gemini + boost",
    "structured_routed@gemini": "his `improved`, exactly as deployed", "R4@gemini": "R4 on his Gemini hybrid + boost",
    "R4f@gemini": "R4f (fused) on his Gemini hybrid + boost", "R4-routed@gemini": "R4 on his `improved` first stage",
    "D3@gemini": "D3: his `improved` + MiniLM reranker", "D3i@gemini": "D3i (as shipped): his `improved` + int8 ONNX MiniLM, top 20, fused",
}
FAMILY = {c: "teammate" for c in FLAT_ORDER[:8]} | {c: "exp3" for c in ["R4", "R4f", "R4-routed", "R4-bm25", "R4e", "R5", "R5f"]} | {"D1": "cpu", "D2": "cpu", "D1i": "cpu"}     | {c: "teammate" for c in ["naive_dense@gemini", "structured_dense@gemini", "structured_hybrid@gemini", "structured_hybrid_boost@gemini",
                               "structured_routed@gemini"]} | {c: "exp3" for c in ["R4@gemini", "R4f@gemini", "R4-routed@gemini"]}     | {"D3@gemini": "cpu", "D3i@gemini": "cpu"}
COLOUR = {"teammate": "#eb6834", "exp3": "#2a78d6", "cpu": "#1baf7a"}   # dataviz reference slots 2, 1, 3 (validated)
METRICS = [("budget_recall", "Recall @ 2,500 tokens"), ("rr10", "MRR@10"), ("recall5", "Recall@5"), ("ndcg10", "nDCG@10")]
COMPARISONS = [
    ("structured_routed@gemini", "naive_dense@gemini", "his claim on his own Gemini index: `improved` vs `baseline`"),
    ("structured_routed@bge-m3", "naive_dense@bge-m3", "his claim: structure + routing vs naive dense"),
    ("R4", "structured_hybrid_boost@bge-m3", "adding the reranker"),
    ("R4", "structured_routed@bge-m3", "reranker vs his routing rule"),
    ("R4-routed", "R4", "is routing still needed after reranking?"),
    ("R4-bm25", "structured_bm25_boost", "reranker on BM25 only (no embeddings at all)"),
    ("R4e", "R4", "Qwen3-Embedding-0.6B vs BGE-M3"),
    ("R4f", "R4", "fusing the reranker with the first stage instead of replacing it"),
    ("R5", "R4", "contextual chunk enrichment"),
    ("R5f", "R4f", "contextual chunk enrichment (fused)"),
    ("R5", "structured_routed@bge-m3", "full Experiment 3 pipeline vs his `improved`"),
    ("D1", "structured_bm25_boost", "CPU MiniLM reranker on his BM25 fallback"),
    ("D2", "structured_routed@bge-m3", "CPU stack (bge-small + MiniLM) vs his `improved`"),
    ("D1i", "structured_bm25_boost", "the shipped integration on his no-key fallback"),
    ("R4@gemini", "structured_hybrid_boost@gemini", "adding the reranker to his Gemini hybrid"),
    ("R4f@gemini", "structured_routed@gemini", "fused reranker vs his `improved`, both on Gemini"),
    ("R4-routed@gemini", "structured_routed@gemini", "reranker on top of his `improved`"),
    ("D3i@gemini", "structured_routed@gemini", "the shipped integration vs his `improved` as deployed"),
]
GRAPH_ORDER = ["R5@budget", "R6-onehop", "R6a", "R6c", "R6d", "R5+expand", "R6x", "R6y",
               "structured_routed@gemini@budget", "R6-onehop@gemini", "R6a@gemini", "R6c@gemini", "R6d@gemini",
               "structured_routed@gemini+expand", "R6x@gemini", "R6y@gemini"]
GRAPH_LABEL = {"R5@budget": "R5, flat (same budget)", "R6-onehop": "R5 + his one-hop expansion (inside the budget)",
               "R6a": "R6a: BFS depth 2", "R6c": "R6c: A*, admissible heuristic", "R6d": "R6d: A*, tuned on dev",
               "R5+expand": "R5 + his one-hop expansion after the budget",
               "R6x": "R6x: R5 + A* dependencies after the budget (in place of his expansion)",
               "R6y": "R6y: R6x with dependency edges only, retuned on dev",
               "R6y@gemini": "R6y: his hits + A* over dependency edges only",
               "structured_routed@gemini@budget": "his `improved` (Gemini), flat", "R6-onehop@gemini": "his `improved` + his one-hop expansion",
               "R6a@gemini": "his `improved` seeds, BFS", "R6c@gemini": "his `improved` seeds, A* admissible",
               "R6d@gemini": "his `improved` seeds, A* tuned on dev",
               "structured_routed@gemini+expand": "his `improved` exactly as his app sends it: hits + one-hop expansion",
               "R6x@gemini": "R6x: his hits + A* dependencies in place of his expansion"}
GRAPH_METRICS = [("budget_recall", "gold units in evidence"), ("hit_dependencies_complete", "flat hits' dependencies resolved"),
                 ("refers_to_complete", "cross-refs resolved"), ("defined_in_complete", "definitions resolved"),
                 ("continues_complete", "split provisions whole"), ("dependencies_complete", "all dependencies"),
                 ("dependencies_resolved", "resolved (count)"), ("dependencies_unresolved", "unresolved (count)"),
                 ("evidence_tokens", "tokens")]
COUNTS = ("evidence_tokens", "dependencies_resolved", "dependencies_unresolved")
GRAPH_COMPARISONS = [("R6d", "R5@budget", "A* (tuned) vs flat, same budget"), ("R6d", "R6-onehop", "A* vs his one-hop expansion"),
                     ("R6d", "R6a", "A* vs BFS"), ("R6c", "R5@budget", "A* (admissible) vs flat"),
                     ("R6d@gemini", "structured_routed@gemini@budget", "A* on his `improved` vs his flat context"),
                     ("R6d@gemini", "R6-onehop@gemini", "A* vs his one-hop expansion, both on his ranking"),
                     ("R6x", "R5+expand", "A* dependencies vs his expansion, after the R5 hits"),
                     ("R6x@gemini", "structured_routed@gemini+expand", "A* dependencies vs his expansion, in his deployed layout"),
                     ("R6y", "R5+expand", "dependency-only A* vs his expansion, after the R5 hits"),
                     ("R6y@gemini", "structured_routed@gemini+expand", "dependency-only A* vs his expansion, in his deployed layout"),
                     ("R6y@gemini", "R6x@gemini", "R6y vs R6x: dependency edges only, retuned")]
SETS = [("reference", None, "Teammate's questions (25 answerable)"), ("heldout", "test", "Held-out test split")]


def _select(rows, qset, split):
    return [r for r in rows if r["qset"] == qset and (split is None or r["split"] == split) and r["answerable"]]


def _mean(rows, cond, metric):
    vals = [r[metric] for r in rows if r["condition"] == cond and r.get(metric) is not None]
    return float(np.mean(vals)) if vals else float("nan")


def _ci(vals, n=2000, seed=0):
    vals = np.asarray(vals, dtype=float)
    rng = np.random.default_rng(seed)
    boots = vals[rng.integers(0, len(vals), size=(n, len(vals)))].mean(axis=1)
    return float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def paired(rows, a, b, metric):
    ra = {r["qid"]: r[metric] for r in rows if r["condition"] == a and r.get(metric) is not None}
    rb = {r["qid"]: r[metric] for r in rows if r["condition"] == b and r.get(metric) is not None}
    q = sorted(set(ra) & set(rb))
    if not q:
        return None
    d = np.array([ra[x] - rb[x] for x in q])
    lo, hi = _ci(d)
    nz = d[d != 0]
    p = float(wilcoxon(nz).pvalue) if len(nz) >= 2 else float("nan")
    return dict(mean=float(d.mean()), lo=lo, hi=hi, p=p, n=len(q), wins=int((d > 0).sum()), losses=int((d < 0).sum()))


def _fmt_diff(c):
    if c is None:
        return "–", "–", "–"
    s = f"{c['mean']:+.3f} [{c['lo']:+.3f}, {c['hi']:+.3f}]"
    if c["lo"] > 0 or c["hi"] < 0:
        s = f"**{s}**"
    return s, ("–" if np.isnan(c["p"]) else f"{c['p']:.3f}"), f"{c['wins']}/{c['losses']}"


def flat_tables(rows, out: list[str]) -> None:
    for qset, split, title in SETS:
        sub = _select(rows, qset, split)
        if not sub:
            continue
        n = len({r["qid"] for r in sub})
        out += [f"### {title} (n = {n})", "", "| Condition | " + " | ".join(m for _, m in METRICS) + " |", "|---|" + "---|" * len(METRICS)]
        for c in [c for c in FLAT_ORDER if any(r["condition"] == c for r in sub)]:
            cells = []
            for m, _ in METRICS:
                v = _mean(sub, c, m)
                if m == "budget_recall":
                    lo, hi = _ci([r[m] for r in sub if r["condition"] == c])
                    cells.append(f"{v:.3f} [{lo:.2f}, {hi:.2f}]")
                else:
                    cells.append(f"{v:.3f}")
            out.append(f"| `{c}` {LABEL.get(c, '')} | " + " | ".join(cells) + " |")
        out.append("")
        types = sorted({r["type"] for r in sub}, key=["natural", "section_ref", "old_number"].index)
        counts = {t: len({r["qid"] for r in sub if r["type"] == t}) for t in types}
        out += [f"Recall @ 2,500 tokens by question type ({title.lower()}):", "",
                "| Condition | " + " | ".join(f"{t} (n={counts[t]})" for t in types) + " |", "|---|" + "---|" * len(types)]
        for c in [c for c in FLAT_ORDER if any(r["condition"] == c for r in sub)]:
            out.append(f"| `{c}` | " + " | ".join(f"{_mean([r for r in sub if r['type'] == t], c, 'budget_recall'):.3f}" for t in types) + " |")
        out.append("")


def reproduction_table(rows, out: list[str]) -> None:
    sub = _select(rows, "reference", None)
    out += ["| Config | Published (his Gemini run) R@5 / MRR / R@2,500 | This repo R@5 / MRR / R@2,500 | Match |", "|---|---|---|---|"]
    for cfg, pub in PUBLISHED.items():
        mine = cfg if "bm25" in cfg else f"{cfg}@gemini"   # BM25-only rows need no embedder: same code, same index
        if not any(r["condition"] == mine for r in sub):
            mine = f"{cfg}@bge-m3"
        if not any(r["condition"] == mine for r in sub):
            continue
        vals = tuple(round(_mean(sub, mine, m), 2) for m in ("recall5", "rr10", "budget_recall"))
        same = "exact" if vals == pub else ("n/a: BGE-M3 in place of Gemini" if mine.endswith("@bge-m3") else "differs")
        out.append(f"| `{cfg}` | {pub[0]:.2f} / {pub[1]:.2f} / {pub[2]:.2f} | {vals[0]:.2f} / {vals[1]:.2f} / {vals[2]:.2f} (`{mine}`) | {same} |")
    out.append("")


def comparison_tables(rows, comparisons, metrics, out: list[str], graph=False) -> None:
    for qset, split, title in SETS:
        sub = _select(rows, qset, split)
        if not sub:
            continue
        out += [f"#### {title}", "", "| A | B | Question | Metric | Mean A − B [95% CI] | Wilcoxon p | A higher / lower |", "|---|---|---|---|---|---|---|"]
        for a, b, what in comparisons:
            for m, mlabel in metrics:
                s, p, wl = _fmt_diff(paired(sub, a, b, m))
                out.append(f"| `{a}` | `{b}` | {what} | {mlabel} | {s} | {p} | {wl} |")
        out.append("")


def graph_tables(rows, tuning: dict, out: list[str]) -> None:
    for seed, t in tuning.items():
        b = t["best"]
        out += [f"A* seeded by `{seed}`, tuned on the held-out dev split: λ = {b['lam']}, μ = {b['mu']}, {b['seeds']} seeds "
                f"(objective {b['objective']:.3f}).", ""]
        if t.get("expand"):
            x = t["expand"]
            out += [f"R6x after the `{seed}` hits: {x['allowance']} extra tokens (his expansion's mean on dev), "
                    f"λ = {x['best']['lam']}, μ = {x['best']['mu']} tuned on dev (objective {x['best']['objective']:.3f}).", ""]
        if t.get("expand_dep"):
            y = t["expand_dep"]
            out += [f"R6y after the `{seed}` hits: the same {y['allowance']} tokens, dependency edges only, λ = {y['best']['lam']}, "
                    f"μ = {y['best']['mu']} tuned on dev for gold units and the flat hits' dependencies (objective "
                    f"{y['best']['objective']:.3f}).", ""]
    out += ["*Flat hits' dependencies resolved* has a fixed denominator per question: the dependencies of the flat budgeted "
            "hits of the same ranking. *All dependencies* is over whatever the evidence contains, so an expansion that adds "
            "chunks with their own unresolved references scores lower on it even when it resolves more of the hits' needs.", ""]
    for qset, split, title in SETS:
        sub = _select(rows, qset, split)
        if not sub:
            continue
        out += [f"#### {title}", "", "| Condition | " + " | ".join(m for _, m in GRAPH_METRICS) + " |", "|---|" + "---|" * len(GRAPH_METRICS)]
        for c in [c for c in GRAPH_ORDER if any(r["condition"] == c for r in sub)]:
            out.append(f"| `{c}` {GRAPH_LABEL[c]} | " + " | ".join(
                (f"{_mean(sub, c, m):.1f}" if m in COUNTS[1:] else f"{_mean(sub, c, m):.0f}" if m == "evidence_tokens"
                 else f"{_mean(sub, c, m):.3f}") for m, _ in GRAPH_METRICS) + " |")
        out.append("")


def gate_table(gate: dict, out: list[str]) -> None:
    out += ["| Condition | τ (dev) | Held-out test: out-of-scope refused | answerable refused | Reference: out-of-scope refused | answerable refused |",
            "|---|---|---|---|---|---|"]
    for c, g in gate.items():
        t, r = g["test"], g["reference"]
        out.append(f"| `{c}` | {g['tau']:.4f} | {t['oos_refused']:.2f} (n={t['n_oos']}) | {t['answerable_refused']:.2f} (n={t['n_answerable']}) "
                   f"| {r['oos_refused']:.2f} (n={r['n_oos']}) | {r['answerable_refused']:.2f} (n={r['n_answerable']}) |")
    out.append("")


def plot(rows, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    surface, ink, ink2, grid = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
    sets = [(q, s, t) for q, s, t in SETS if _select(rows, q, s)]
    conds = [c for c in FLAT_ORDER if any(r["condition"] == c for r in rows)][::-1]
    fig, axes = plt.subplots(len(sets), 2, figsize=(12, 0.36 * len(conds) * len(sets) + 1.6), facecolor=surface, squeeze=False)
    for row, (qset, split, title) in enumerate(sets):
        sub = _select(rows, qset, split)
        for col, (m, mlabel) in enumerate(METRICS[:2]):
            ax = axes[row][col]
            vals = [_mean(sub, c, m) for c in conds]
            ax.set_facecolor(surface)
            ax.barh(range(len(conds)), vals, height=0.62, color=[COLOUR[FAMILY[c]] for c in conds], edgecolor=surface, linewidth=2)
            for y, v in enumerate(vals):
                ax.text(v + 0.012, y, f"{v:.2f}", va="center", fontsize=8.5, color=ink)
            ax.set_yticks(range(len(conds)))
            ax.set_yticklabels(conds if col == 0 else [], fontsize=8.5, color=ink2)
            ax.set_xlim(0, 1.1)
            ax.set_title(f"{mlabel} · {title}", loc="left", fontsize=10.5, color=ink)
            ax.grid(axis="x", color=grid, linewidth=0.8)
            ax.set_axisbelow(True)
            for side in ("top", "right", "left"):
                ax.spines[side].set_visible(False)
            ax.spines["bottom"].set_color(grid)
            ax.tick_params(colors=ink2, length=0)
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLOUR[k]) for k in ("teammate", "exp3", "cpu")]
    fig.legend(handles, ["teammate's configs (BGE-M3 in place of Gemini)", "Experiment 3 methods (GPU)", "CPU-deployable (Render free tier)"],
               loc="lower center", ncol=3, frameon=False, labelcolor=ink2, fontsize=9, bbox_to_anchor=(0.5, -0.005))
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=180, facecolor=surface)
    plt.close(fig)


def report(out_dir: Path, provenance: dict) -> None:
    rows = read_jsonl(out_dir / "per_query.jsonl")
    lines = ["# TaxRAG: Experiment 3 methods on the BC3415 tax corpus", "",
             "Generated by `python eval/tax_experiment.py report`. Write-up: `docs/taxrag-results.md`.", "",
             "```", json.dumps(provenance, indent=1), "```", "", "## Reproduction of the teammate's numbers", ""]
    reproduction_table(rows, lines)
    lines += ["## Flat retrieval", ""]
    flat_tables(rows, lines)
    lines += ["## Paired comparisons (flat retrieval)", "",
              "Mean per-question difference A − B with a 95% paired bootstrap CI (2,000 resamples) and a two-sided Wilcoxon signed-rank "
              "p-value (ties dropped). **Bold**: the CI excludes 0.", ""]
    comparison_tables(rows, COMPARISONS, [("budget_recall", "R@2,500"), ("rr10", "MRR@10")], lines)
    gpath = out_dir / "graph_per_query.jsonl"
    if gpath.exists():
        grows = read_jsonl(gpath)
        tuning = json.loads((out_dir / "graph_tuning.json").read_text(encoding="utf-8"))
        lines += ["## Graph expansion at the same 2,500-token budget", ""]
        graph_tables(grows, tuning, lines)
        lines += ["### Paired comparisons (graph)", ""]
        comparison_tables(grows, GRAPH_COMPARISONS, [("budget_recall", "gold units in evidence"),
                                                      ("hit_dependencies_complete", "flat hits' dependencies resolved"),
                                                      ("dependencies_complete", "all dependencies resolved"),
                                                      ("dependencies_unresolved", "unresolved (count, lower is better)")], lines, graph=True)
    gate_path = out_dir / "gate.json"
    if gate_path.exists():
        lines += ["## Calibrated abstention (refuse when the best reranker score, or the best dense similarity without one, < τ)", ""]
        gate_table(json.loads(gate_path.read_text(encoding="utf-8")), lines)
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    fig_dir = out_dir / "figures"
    fig_dir.mkdir(exist_ok=True)
    plot(rows, fig_dir / "retrieval.png")
    print(f"wrote {out_dir / 'summary.md'} and {fig_dir / 'retrieval.png'}")
