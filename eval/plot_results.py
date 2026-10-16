"""Static figures for the Experiment 3 write-up (reads eval/results/exp3/summary.csv).

One chart per question, one axis each, single-series bars in categorical slot 1 with 95% CI whiskers.
The tables in summary.md are the accessible table view of the same numbers.
Usage:  python eval/plot_results.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import ROOT  # noqa: E402

RES = ROOT / "eval" / "results" / "exp3"
FIG = RES / "figures"
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
ORDER = ["Ref-BM25", "R1", "R2", "R3", "R4", "R4e", "R4q", "R5", "R5@budget", "R6a", "R6b", "R6c", "R6d"]


def load() -> list[dict]:
    with open(RES / "summary.csv", encoding="utf-8") as f:
        return [dict(r, mean=float(r["mean"]), ci_low=float(r["ci_low"]), ci_high=float(r["ci_high"])) for r in csv.DictReader(f)]


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK2, length=0)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def bars(rows, dataset, metric, title, xlabel, fname):
    sel = [r for r in rows if r["dataset"] == dataset and r["metric"] == metric]
    sel.sort(key=lambda r: ORDER.index(r["condition"]) if r["condition"] in ORDER else 99)
    if not sel:
        return
    fig, ax = plt.subplots(figsize=(7, 0.42 * len(sel) + 1.3), facecolor=SURFACE)
    style(ax)
    y = list(range(len(sel)))[::-1]
    means = [r["mean"] for r in sel]
    err = [[r["mean"] - r["ci_low"] for r in sel], [r["ci_high"] - r["mean"] for r in sel]]
    ax.barh(y, means, height=0.6, color=SERIES[0], edgecolor=SURFACE, linewidth=2)
    ax.errorbar(means, y, xerr=err, fmt="none", ecolor=INK2, elinewidth=1, capsize=3)
    for yi, r in zip(y, sel):
        ax.text(r["ci_high"] + 0.01, yi, f"{r['mean']:.3f}", va="center", fontsize=9, color=INK)
    ax.set_yticks(y, [r["condition"] for r in sel], color=INK)
    ax.set_xlim(0, min(1.0, max(r["ci_high"] for r in sel) * 1.18 + 0.02))
    ax.set_xlabel(xlabel, color=INK2)
    ax.set_title(title, loc="left", color=INK, fontsize=11)
    fig.tight_layout()
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / fname, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def graph_chart(rows):
    conds = [c for c in ORDER if any(r["dataset"] == "synthetic-graph" and r["condition"] == c for r in rows)]
    metrics = [("clause_recall", "Clause recall"), ("definition_coverage", "Definition coverage"), ("xref_completeness", "Cross-reference completeness")]
    if not conds:
        return
    fig, ax = plt.subplots(figsize=(7.5, 4.3), facecolor=SURFACE)
    style(ax)
    ax.xaxis.grid(False)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    w = 0.26
    for k, (m, label) in enumerate(metrics):
        vals = [next(r["mean"] for r in rows if r["dataset"] == "synthetic-graph" and r["condition"] == c and r["metric"] == m) for c in conds]
        xs = [i + (k - 1) * (w + 0.02) for i in range(len(conds))]
        ax.bar(xs, vals, width=w, color=SERIES[k], edgecolor=SURFACE, linewidth=2, label=label)
    ax.set_xticks(range(len(conds)), conds, color=INK)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Share (test split)", color=INK2)
    ax.set_title("Graph expansion at an equal 1,200-token budget (synthetic)", loc="left", color=INK, fontsize=11)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3, fontsize=9, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(FIG / "synthetic_graph.png", dpi=160, facecolor=SURFACE)
    plt.close(fig)


def main():
    rows = load()
    bars(rows, "synthetic", "ndcg@10", "Synthetic clause library: nDCG@10 by condition (90 test requests)", "nDCG@10", "synthetic_ndcg10.png")
    bars(rows, "synthetic", "recall@5", "Synthetic clause library: Recall@5 by condition", "Recall@5 (relevant clauses in top-5 chunks)", "synthetic_recall5.png")
    bars(rows, "acord-test", "ndcg@10", "ACORD test (57 queries): nDCG@10 by condition", "nDCG@10", "acord_ndcg10.png")
    bars(rows, "lbr-mini", "char_r@8kchars", "LegalBench-RAG-mini (776 queries): recall within 8,000 retrieved characters",
         "Share of gold characters retrieved (equal ~2,000-token budget)", "lbr_recall_8kchars.png")
    graph_chart(rows)
    print("figures in", FIG)


if __name__ == "__main__":
    main()
