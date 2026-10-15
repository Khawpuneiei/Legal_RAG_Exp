"""Run Experiment 3 (retrieval conditions) on the synthetic clause library, ACORD and LegalBench-RAG-mini.

Usage:
  python eval/run_experiment.py --config configs/experiments/exp3.yaml
  python eval/run_experiment.py --datasets synthetic --conditions R1 R4 R6c

Writes eval/results/exp3/:
  per_query.jsonl   one row per (dataset, condition, query) with all metrics
  rankings.jsonl    top-20 retrieved chunks / clause ids per query (input to the generation eval)
  summary.csv       mean and 95% bootstrap CI per (dataset, condition, metric)
  summary.md        headline tables
  graph_tuning.json R6d grid search on the dev split
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.metrics.retrieval_metrics import bootstrap_ci, chunk_units, query_metrics, unit_ranking  # noqa: E402
from src.common import ROOT, Dataset, load_acord, load_lbr, load_synthetic, read_jsonl  # noqa: E402
from src.retrieval.graph import ClauseGraph, graph_metrics, tokens  # noqa: E402
from src.retrieval.pipeline import Condition, Resources, precompute_llm, rank  # noqa: E402

OUT = ROOT / "eval" / "results" / "exp3"


def load_dataset(name: str) -> Dataset:
    if name == "synthetic":
        return load_synthetic()
    if name == "acord-test":
        return load_acord("test")
    if name == "lbr-mini":
        return load_lbr()
    raise ValueError(name)


def flat_conditions(cfg: dict, names: list[str] | None) -> list[Condition]:
    out = []
    for n, spec in cfg["conditions"].items():
        if names and n not in names:
            continue
        if spec.get("graph"):
            continue
        out.append(Condition(name=n, **spec))
    return out


def run_flat(ds: Dataset, cond: Condition, res: Resources, rows: list, rank_rows: list) -> dict:
    t0 = time.time()
    r = rank(ds, cond, res)
    elapsed = time.time() - t0
    covers = chunk_units(ds, r["chunks"]) if ds.units else None
    for qi, q in enumerate(ds.queries):
        ranking = r["rankings"][qi]
        m = query_metrics(ds, q, ranking, r["chunks"], covers)
        row = dict(dataset=ds.name, condition=cond.name, qid=q.qid, split=q.meta.get("split", "test"),
                   tag=q.tags[0] if q.tags else "", weight=ds.weights.get(q.qid, 1.0), **m)
        rows.append(row)
        top = ranking[:20]
        rr = dict(dataset=ds.name, condition=cond.name, qid=q.qid, chunk_ids=[r["chunks"][i].chunk_id for i in top])
        if covers is not None:
            units, _ = unit_ranking(top, covers)
            rr["unit_ids"] = units
        if cond.query_rewrite:
            rr["query"] = r["queries"][qi]
        rank_rows.append(rr)
    print(f"  {ds.name:10s} {cond.name:8s} done in {elapsed:6.1f}s")
    return r


def run_graph(ds: Dataset, cfg: dict, r5: dict, res: Resources, rows: list, wanted: list[str]) -> dict:
    """R6a-d on the synthetic set, all at the same token budget, against R5 truncated to that budget."""
    clauses = ds.meta["clauses"]
    edges = read_jsonl(ROOT / "data" / "synthetic" / "edges.jsonl")
    emb = res.embedder("bge-m3")
    ids = list(clauses)
    cemb = emb.encode_docs([clauses[i]["text"] for i in ids])
    graph = ClauseGraph(clauses, edges, {i: cemb[k] for k, i in enumerate(ids)})
    q_emb = emb.encode_queries([q.text for q in ds.queries])
    covers = chunk_units(ds, r5["chunks"])
    budget, n_seeds = cfg["graph_token_budget"], cfg["graph_seeds"]

    def seeds_for(qi):
        units, _ = unit_ranking(r5["rankings"][qi], covers)
        return units[:n_seeds]

    def evaluate(strategy, lam=None, mu=None, split=None):
        out = []
        for qi, q in enumerate(ds.queries):
            if split and q.meta["split"] != split:
                continue
            if not any(g >= ds.relevant_grade for g in q.graded.values()):
                continue
            seeds = seeds_for(qi)
            if strategy == "flat":
                units, _ = unit_ranking(r5["rankings"][qi], covers)
                ev, used = [], 0
                for u in units:
                    c = tokens(clauses[u]["text"])
                    if used + c > budget:
                        continue
                    ev.append(u)
                    used += c
                res_ = dict(evidence=ev, tokens=used, expanded=0, seconds=0.0)
            elif strategy == "bfs":
                res_ = graph.bfs(seeds, budget)
            elif strategy == "ppr":
                res_ = graph.ppr(seeds, [1.0 / (i + 1) for i in range(len(seeds))], budget)
            else:
                res_ = graph.astar(seeds, q_emb[qi], budget, lam=lam, mu=mu)
            m = graph_metrics(res_["evidence"], graph, q.graded, ds.relevant_grade)
            m.update(evidence_tokens=res_["tokens"], nodes_expanded=res_["expanded"], ms=1000 * res_["seconds"])
            out.append((q, m))
        return out

    # R6d: tune lambda, mu on dev (objective: mean of clause recall, definition coverage, xref completeness)
    grid = []
    for lam, mu in itertools.product([0.0, 0.2, 0.5, 1.0, 2.0], [0.0, 0.5, 1.0, 2.0]):
        ms = [m for _, m in evaluate("astar", lam, mu, split="dev")]
        obj = float(np.mean([(m["clause_recall"] + m["definition_coverage"] + m["xref_completeness"]) / 3 for m in ms]))
        grid.append(dict(lam=lam, mu=mu, objective=obj))
    best = max(grid, key=lambda g: g["objective"])
    (OUT / "graph_tuning.json").write_text(json.dumps(dict(grid=grid, best=best), indent=2), encoding="utf-8")
    print(f"  R6d tuned on dev: lambda={best['lam']} mu={best['mu']} objective={best['objective']:.3f}")

    plan = {"R5@budget": ("flat", None, None), "R6a": ("bfs", None, None), "R6b": ("ppr", None, None),
            "R6c": ("astar", 0.2, 1.0), "R6d": ("astar", best["lam"], best["mu"])}
    for name, (strategy, lam, mu) in plan.items():
        if name != "R5@budget" and wanted and name not in wanted:
            continue
        for q, m in evaluate(strategy, lam, mu):
            rows.append(dict(dataset="synthetic-graph", condition=name, qid=q.qid, split=q.meta["split"], tag=q.tags[0], weight=1.0, **m))
        print(f"  synthetic  {name:9s} done")
    return best


SUMMARY_METRICS = {
    "synthetic": ["recall@1", "recall@3", "recall@5", "recall@10", "mrr", "ndcg@10", "char_p@5", "char_r@5", "tokens@5"],
    "acord-test": ["ndcg@5", "ndcg@10", "p@5_4star", "p@5_5star", "mrr", "recall@10"],
    "lbr-mini": ["char_p@1", "char_r@1", "char_p@4", "char_r@4", "char_p@16", "char_r@16", "char_r@64"],
    "synthetic-graph": ["clause_recall", "definition_coverage", "xref_completeness", "requires_satisfied", "evidence_tokens", "nodes_expanded", "ms"],
}


def summarize(rows: list[dict]) -> list[dict]:
    out = []
    keyf = lambda r: (r["dataset"], r["condition"])  # noqa: E731
    groups: dict = {}
    for r in rows:
        if r["dataset"].startswith("synthetic") and r["split"] != "test":
            continue  # headline numbers on the held-out test split
        groups.setdefault(keyf(r), []).append(r)
    for (ds, cond), rs in groups.items():
        for metric in SUMMARY_METRICS[ds]:
            vals = [r.get(metric, float("nan")) for r in rs]
            mean, lo, hi = bootstrap_ci(vals, [r["weight"] for r in rs])
            n = int(np.sum(~np.isnan(np.asarray(vals, dtype=float))))
            out.append(dict(dataset=ds, condition=cond, metric=metric, mean=mean, ci_low=lo, ci_high=hi, n=n))
    return out


def write_markdown(summary: list[dict], cfg: dict) -> None:
    lines = ["# Experiment 3 results", "",
             "Generated by `python eval/run_experiment.py`. Mean with 95% bootstrap CI in brackets.",
             "Synthetic numbers use the 90-request held-out test split. LegalBench-RAG-mini weights its four sources equally, as the official script does.", ""]
    order = list(cfg["conditions"]) + ["R5@budget"]
    for ds in SUMMARY_METRICS:
        rows = [s for s in summary if s["dataset"] == ds]
        if not rows:
            continue
        metrics = [m for m in SUMMARY_METRICS[ds] if any(s["metric"] == m for s in rows)]
        conds = sorted({s["condition"] for s in rows}, key=lambda c: order.index(c) if c in order else 99)
        n = max(s["n"] for s in rows)
        lines += [f"## {ds} (n = {n} queries)", "", "| Condition | " + " | ".join(metrics) + " |", "|---|" + "---|" * len(metrics)]
        for c in conds:
            cells = []
            for m in metrics:
                s = next((x for x in rows if x["condition"] == c and x["metric"] == m), None)
                if s is None or np.isnan(s["mean"]):
                    cells.append("–")
                elif m in ("tokens@5", "evidence_tokens", "nodes_expanded", "ms"):
                    cells.append(f"{s['mean']:.0f}")
                else:
                    cells.append(f"{s['mean']:.3f} [{s['ci_low']:.3f}, {s['ci_high']:.3f}]")
            lines.append(f"| {c} | " + " | ".join(cells) + " |")
        lines.append("")
    lines += ["## Conditions", ""] + [f"- **{k}**: {v.get('description', '')}" for k, v in cfg["conditions"].items()] + \
             ["- **R5@budget**: R5's clause ranking truncated to the same token budget as R6 (equal-budget baseline)", ""]
    (OUT / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "configs" / "experiments" / "exp3.yaml"))
    ap.add_argument("--datasets", nargs="*")
    ap.add_argument("--conditions", nargs="*")
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    ds_names = args.datasets or cfg["datasets"]
    datasets = {n: load_dataset(n) for n in ds_names}
    conds = flat_conditions(cfg, args.conditions)
    res = Resources()

    print("Stage 1: LLM pre-computation (contextual chunks, query rewrites) with", cfg["llm"])
    for ds in datasets.values():
        for c in conds:
            if ds.name not in c.skip and (c.contextual or c.query_rewrite):
                precompute_llm(ds, c, res)
    if res.llm:
        res.llm.unload()

    print("Stage 2: retrieval")
    rows, rank_rows, r5 = [], [], None
    for ds in datasets.values():
        for c in conds:
            if ds.name in c.skip:
                continue
            r = run_flat(ds, c, res, rows, rank_rows)
            if ds.name == "synthetic" and c.name == "R5":
                r5 = r
    graph_wanted = [n for n, s in cfg["conditions"].items() if s.get("graph") and (not args.conditions or n in args.conditions)]
    if "synthetic" in datasets and graph_wanted:
        if r5 is None:
            r5 = rank(datasets["synthetic"], Condition(name="R5", **{k: v for k, v in cfg["conditions"]["R5"].items()}), res)
        print("Stage 3: clause-graph expansion")
        run_graph(datasets["synthetic"], cfg, r5, res, rows, graph_wanted)

    with open(OUT / "per_query.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    with open(OUT / "rankings.jsonl", "w", encoding="utf-8") as f:
        for r in rank_rows:
            f.write(json.dumps(r) + "\n")
    summary = summarize(rows)
    with open(OUT / "summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0]))
        w.writeheader()
        w.writerows(summary)
    write_markdown(summary, cfg)
    print("Wrote", OUT / "summary.md")


if __name__ == "__main__":
    main()
