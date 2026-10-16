"""Clause search service: the Experiment 3 winning configuration (R5, plus R6d graph expansion) as a reusable object.

Used by the drafting harnesses (Experiments 1-2) for live queries, and by the API when a GPU/CPU model host is
available. Document embeddings and contextual chunk texts come from the Experiment 3 caches, so building the index
costs no LLM calls. Query embeddings run on CPU; the cross-encoder reranker runs on GPU (fp16) when one is present,
next to the local LLM (about 1.2 GB of VRAM).
"""
from __future__ import annotations

import threading

import numpy as np

from src.common import JsonCache, load_synthetic, read_jsonl, ROOT, stable_hash
from src.llm.ollama import OllamaLLM
from src.retrieval.bm25 import BM25Index
from src.retrieval.chunking import make_chunks
from src.retrieval.contextual import contextualize
from src.retrieval.dense import Embedder
from src.retrieval.graph import ClauseGraph
from src.retrieval.hybrid import rrf
from src.retrieval.rerank import Reranker

TOP_N = 100
RERANK_TOP = 50
TUNED = dict(lam=0.0, mu=2.0)   # eval/results/exp3/graph_tuning.json (R6d)
_LOCK = threading.Lock()


class _CPUQueryEncoder:
    def __init__(self, name: str = "BAAI/bge-m3"):
        self.name = name
        self._model = None
        self.cache = JsonCache("qemb-bge-m3")

    def encode(self, text: str) -> np.ndarray:
        key = stable_hash(self.name, text)
        hit = self.cache.get(key)
        if hit is not None:
            return np.asarray(hit, dtype=np.float32)
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.name, device="cpu")
            self._model.max_seq_length = 1024
        v = self._model.encode([text], normalize_embeddings=True, convert_to_numpy=True)[0].astype(np.float32)
        self.cache.put(key, [round(float(x), 5) for x in v])
        return v


class ClauseSearch:
    def __init__(self, contextual: bool = True, rerank: bool = True):
        ds = load_synthetic()
        self.ds = ds
        self.clauses = ds.meta["clauses"]
        self.chunks = make_chunks(ds, "clause")
        self.chunk_clause = [u.unit_id for u in ds.units]  # clause-level chunks are 1:1 with units
        assert len(self.chunk_clause) == len(self.chunks)
        if contextual:
            self.texts = contextualize(ds, self.chunks, OllamaLLM(num_ctx=8192), "chunk_context")
        else:
            self.texts = [c.text for c in self.chunks]
        emb = Embedder("bge-m3")
        self.doc_emb = emb.encode_docs(self.texts)
        ids = list(self.clauses)
        cemb = emb.encode_docs([self.clauses[i]["text"] for i in ids])
        self.graph = ClauseGraph(self.clauses, read_jsonl(ROOT / "data" / "synthetic" / "edges.jsonl"), {i: cemb[k] for k, i in enumerate(ids)})
        emb.unload()
        self.bm25 = BM25Index(self.texts)
        self.qenc = _CPUQueryEncoder()
        self.reranker = Reranker() if rerank else None
        self.cache = JsonCache("clause-search")

    def search(self, query: str, k: int = 8, agreement_type: str | None = None) -> list[dict]:
        """Hybrid BM25 + dense (RRF), cross-encoder rerank of the top 50, deduplicated to clause ids.
        If agreement_type is given, clauses not approved for that type are filtered out after ranking."""
        key = stable_hash("search-v1", query, str(k), str(agreement_type), str(self.reranker is not None))
        with _LOCK:
            hit = self.cache.get(key)
        if hit is not None:
            return hit
        with _LOCK:
            q = self.qenc.encode(query)
            bm = [i for i, _ in self.bm25.search(query, TOP_N)]
            dn = list(np.argsort(-(self.doc_emb @ q))[:TOP_N])
            ranking = [i for i, _ in rrf([bm, [int(i) for i in dn]], top_n=TOP_N)]
            scores = {}
            if self.reranker is not None:
                head = ranking[:RERANK_TOP]
                s = self.reranker.score(query, [self.texts[i] for i in head])
                scores = dict(zip(head, s))
                head = [i for _, i in sorted(zip(s, head), key=lambda x: -x[0])]
                ranking = head + ranking[RERANK_TOP:]
        out, seen = [], set()
        for i in ranking:
            cid = self.chunk_clause[i]
            if cid in seen:
                continue
            seen.add(cid)
            c = self.clauses[cid]
            if agreement_type and agreement_type not in c["templates"] and "ALL" not in c["templates"]:
                continue
            out.append(dict(clause_id=cid, title=c["title"], variant=c["variant"], deviation_cost=c["deviation_cost"],
                            score=round(float(scores.get(i, 0.0)), 4)))
            if len(out) >= k:
                break
        with _LOCK:
            self.cache.put(key, out)
        return out

    def evidence(self, query: str, budget: int = 1200, n_seeds: int = 5, agreement_type: str | None = None) -> list[str]:
        """R6d: R5 seeds expanded with A* over the clause graph (definitions, cross-references, legal requirements)."""
        seeds = [h["clause_id"] for h in self.search(query, k=n_seeds, agreement_type=agreement_type)]
        res = self.graph.astar(seeds, self.qenc.encode(query), budget, **TUNED)
        return res["evidence"]

    def unload(self) -> None:
        if self.reranker is not None:
            self.reranker.unload()
