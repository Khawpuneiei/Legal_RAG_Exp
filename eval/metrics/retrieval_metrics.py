"""Retrieval metrics for Experiment 3.

* Unit level (clauses): Recall@k over the top-k chunks, MRR, nDCG@10 over the induced clause ranking.
  A chunk covers a clause if it overlaps at least half of the clause's characters.
* Character level (LegalBench-RAG): precision and recall of retrieved characters against gold spans,
  computed exactly as legalbenchrag/run_benchmark.py does.
* ACORD, following the paper's protocol (Wang et al. 2025, appendix C.5 and F.1): query-clause pairs
  missing from the qrels are ignored during evaluation (removed from the ranking), nDCG uses linear
  gains as in pytrec_eval, and k-star precision@5 counts top-5 clauses rated >= k stars divided by
  min(5, number of clauses rated >= k for that query).
nDCG uses linear gains (rel / log2(rank + 1)) on every dataset.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from src.common import Dataset
from src.retrieval.chunking import Chunk


def chunk_units(ds: Dataset, chunks: list[Chunk], min_cover: float = 0.5) -> list[list[str]]:
    by_doc = defaultdict(list)
    for u in ds.units:
        by_doc[u.doc_id].append(u)
    out = []
    for c in chunks:
        covered = []
        for u in by_doc.get(c.doc_id, []):
            ov = min(c.end, u.end) - max(c.start, u.start)
            if ov > 0 and ov >= min_cover * (u.end - u.start):
                covered.append(u.unit_id)
        out.append(covered)
    return out


def unit_ranking(ranked_chunks: list[int], covers: list[list[str]]) -> tuple[list[str], list[int]]:
    """Induced unit ranking and, for each unit, the chunk rank (1-based) at which it first appears."""
    seen, units, ranks = set(), [], []
    for r, ci in enumerate(ranked_chunks, 1):
        for u in covers[ci]:
            if u not in seen:
                seen.add(u)
                units.append(u)
                ranks.append(r)
    return units, ranks


def dcg(gains: list[float]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg_at(units: list[str], graded: dict[str, int], k: int) -> float:
    gains = [graded.get(u, 0) for u in units[:k]]
    ideal = sorted(graded.values(), reverse=True)[:k]
    idcg = dcg(ideal)
    return dcg(gains) / idcg if idcg > 0 else float("nan")


def char_pr(ranked_chunks: list[int], chunks: list[Chunk], gold: list[tuple[str, int, int]], k: int) -> tuple[float, float]:
    top = [chunks[i] for i in ranked_chunks[:k]]
    retrieved = sum(c.end - c.start for c in top)
    relevant = sum(e - s for _, s, e in gold)
    hit_p = sum(max(0, min(c.end, e) - max(c.start, s)) for c in top for d, s, e in gold if d == c.doc_id)
    precision = hit_p / retrieved if retrieved else 0.0
    recall = hit_p / relevant if relevant else 0.0
    return precision, recall


def query_metrics(ds: Dataset, q, ranked_chunks: list[int], chunks: list[Chunk], covers: list[list[str]] | None,
                  ks=(1, 3, 5, 10), char_ks=(1, 2, 4, 5, 8, 10, 16, 32, 64)) -> dict:
    m: dict[str, float] = {}
    for k in ks:
        m[f"tokens@{k}"] = sum(len(chunks[i].text) for i in ranked_chunks[:k]) / 4
    if covers is not None and q.graded:
        units, ranks = unit_ranking(ranked_chunks, covers)
        if ds.meta.get("judged_only"):
            # ACORD: unjudged clauses are ignored, i.e. removed from the ranking (ranks renumbered)
            units = [u for u in units if u in q.graded]
            ranks = list(range(1, len(units) + 1))
        rel = {u for u, g in q.graded.items() if g >= ds.relevant_grade}
        if rel:
            for k in ks:
                hit = {u for u, r in zip(units, ranks) if r <= k}
                m[f"recall@{k}"] = len(rel & hit) / len(rel)
            first = next((r for u, r in zip(units, ranks) if u in rel), None)
            m["mrr"] = 1.0 / first if first else 0.0
            m["ndcg@10"] = ndcg_at(units, q.graded, 10)
            m["ndcg@5"] = ndcg_at(units, q.graded, 5)
            top5 = units[:5]
            if ds.name.startswith("acord"):
                for stars, thr in (("3star", 2), ("4star", 3), ("5star", 4)):
                    viable = sum(1 for g in q.graded.values() if g >= thr)
                    hits = sum(1 for u in top5 if q.graded.get(u, 0) >= thr)
                    m[f"p@5_{stars}"] = hits / min(5, viable) if viable else float("nan")
    if q.spans:
        for k in char_ks:
            p, r = char_pr(ranked_chunks, chunks, q.spans, k)
            m[f"char_p@{k}"] = p
            m[f"char_r@{k}"] = r
        # Equal-budget comparison across chunk sizes: take chunks in rank order while the total stays
        # within 8,000 characters (~2,000 tokens), e.g. 4 fixed 2,000-char chunks or ~16 500-char chunks.
        used, n = 0, 0
        for i in ranked_chunks:
            size = chunks[i].end - chunks[i].start
            if used + size > 8000:
                break
            used += size
            n += 1
        p, r = char_pr(ranked_chunks, chunks, q.spans, n)
        m["char_p@8kchars"] = p
        m["char_r@8kchars"] = r
    return m


def bootstrap_ci(values: list[float], weights: list[float] | None = None, n: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    v = np.asarray(values, dtype=float)
    w = np.ones_like(v) if weights is None else np.asarray(weights, dtype=float)
    mask = ~np.isnan(v)
    v, w = v[mask], w[mask]
    if len(v) == 0:
        return float("nan"), float("nan"), float("nan")
    mean = float(np.sum(v * w) / np.sum(w))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(v), size=(n, len(v)))
    boots = np.sum(v[idx] * w[idx], axis=1) / np.sum(w[idx], axis=1)
    return mean, float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))
