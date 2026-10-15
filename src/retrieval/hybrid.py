"""Reciprocal Rank Fusion of lexical and dense rankings (plan R3)."""
from __future__ import annotations


def rrf(rankings: list[list[int]], k: int = 60, top_n: int = 100) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])[:top_n]
