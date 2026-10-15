"""Dense retrieval with sentence-transformers, embeddings cached on disk (plan R1/R2, R4e)."""
from __future__ import annotations

import gc

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from src.common import CACHE, stable_hash

# Model-specific query handling. BGE-M3 uses no instruction for retrieval queries;
# Qwen3-Embedding uses its built-in "query" prompt.
MODELS = {
    "bge-m3": dict(name="BAAI/bge-m3", query_prompt_name=None, max_seq_length=1024),
    "qwen3-emb-0.6b": dict(name="Qwen/Qwen3-Embedding-0.6B", query_prompt_name="query", max_seq_length=1024),
}


class Embedder:
    def __init__(self, key: str, batch_size: int = 32):
        self.key = key
        self.cfg = MODELS[key]
        self.batch_size = batch_size
        self._model = None

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            kwargs = {}
            if torch.cuda.is_available():
                kwargs["model_kwargs"] = {"torch_dtype": torch.float16}
            self._model = SentenceTransformer(self.cfg["name"], device="cuda" if torch.cuda.is_available() else "cpu", **kwargs)
            self._model.max_seq_length = self.cfg["max_seq_length"]
        return self._model

    def encode_docs(self, texts: list[str]) -> np.ndarray:
        path = CACHE / "emb" / self.key / f"{stable_hash(*texts)}.npy"
        if path.exists():
            return np.load(path)
        # sort by length for efficient batching, then restore order
        order = np.argsort([-len(t) for t in texts])
        emb = self.model.encode([texts[i] for i in order], batch_size=self.batch_size, normalize_embeddings=True,
                                show_progress_bar=len(texts) > 2000, convert_to_numpy=True)
        out = np.empty_like(emb)
        out[order] = emb
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, out.astype(np.float32))
        return out.astype(np.float32)

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        path = CACHE / "emb" / self.key / f"q-{stable_hash(*texts)}.npy"
        if path.exists():
            return np.load(path)
        kw = {"prompt_name": self.cfg["query_prompt_name"]} if self.cfg["query_prompt_name"] else {}
        emb = self.model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True, convert_to_numpy=True, **kw).astype(np.float32)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, emb)
        return emb

    def unload(self) -> None:
        self._model = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def dense_search(q_emb: np.ndarray, d_emb: np.ndarray, top_n: int) -> list[list[tuple[int, float]]]:
    scores = q_emb @ d_emb.T
    top = np.argsort(-scores, axis=1)[:, :top_n]
    return [[(int(j), float(scores[i, j])) for j in row] for i, row in enumerate(top)]
