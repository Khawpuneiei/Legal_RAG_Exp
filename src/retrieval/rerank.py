"""Cross-encoder reranking (plan R4)."""
from __future__ import annotations

import gc

import torch
from sentence_transformers import CrossEncoder

from src.common import JsonCache, stable_hash


class Reranker:
    def __init__(self, name: str = "BAAI/bge-reranker-v2-m3", max_length: int = 512, batch_size: int = 32):
        self.name = name
        self.max_length = max_length
        self.batch_size = batch_size
        self._model = None
        self.cache = JsonCache("rerank-" + name.replace("/", "_"))

    @property
    def model(self) -> CrossEncoder:
        if self._model is None:
            kw = {"model_kwargs": {"torch_dtype": torch.float16}} if torch.cuda.is_available() else {}
            self._model = CrossEncoder(self.name, max_length=self.max_length, device="cuda" if torch.cuda.is_available() else "cpu", **kw)
        return self._model

    def score(self, query: str, texts: list[str]) -> list[float]:
        key = stable_hash(self.name, query, *texts)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        scores = self.model.predict([(query, t) for t in texts], batch_size=self.batch_size, show_progress_bar=False)
        scores = [float(s) for s in scores]
        self.cache.put(key, scores)
        return scores

    def unload(self) -> None:
        self._model = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
