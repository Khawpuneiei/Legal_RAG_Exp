"""Lexical retrieval (BM25, plan R3)."""
from __future__ import annotations

import re

import numpy as np
from rank_bm25 import BM25Okapi

_STOP = set("""a an and are as at be by for from has have in is it its of on or that the this to was were will with shall
any all not no may such each other under which who whose than then there these those our we us they their them you your""".split())


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOP]


class BM25Index:
    def __init__(self, texts: list[str]):
        self.bm25 = BM25Okapi([tokenize(t) for t in texts])

    def search(self, query: str, top_n: int) -> list[tuple[int, float]]:
        scores = self.bm25.get_scores(tokenize(query))
        idx = np.argsort(-scores)[:top_n]
        return [(int(i), float(scores[i])) for i in idx]
