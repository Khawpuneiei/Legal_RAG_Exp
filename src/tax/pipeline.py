"""Experiment 3 conditions on the TaxRAG corpus.

First stage = the teammate's own `Retriever` (rag.retrieve: his BM25 index, RRF, section boost, query routing),
with a local embedder injected where his app calls Gemini, so his configs run unchanged and offline. The
Experiment 3 methods are then added on top, exactly as on the legal clause library:

* R4  a cross-encoder reranker over the fused top 50 (BAAI/bge-reranker-v2-m3)
* R5  R4 + contextual chunk enrichment (src/tax/contextual.py) for BM25, the embedder and the reranker
* R6  graph expansion of the R5 seeds at the same 2,500-token budget (src/tax/graph.py): one hop (the
      teammate's `expand`), BFS, A* with the admissible heuristic, A* tuned on the dev split
* gate  calibrated abstention: refuse when the best reranker score is below tau (tuned on the dev split)
* D1, D2  CPU-only variants that fit the teammate's Render free tier (no torch, 512 MB): a MiniLM
      cross-encoder, and bge-small-en-v1.5 in place of Gemini

The teammate's `Retriever.search` only opens Chroma when a corpus has no dense index yet, so setting
`corpus.dense` to `LocalDense` and passing `QueryEmbedder` is enough; none of his code is modified.
"""
from __future__ import annotations

import numpy as np

from src.common import ROOT, JsonCache, stable_hash
from src.retrieval.dense import Embedder
from src.tax.corpus import TAX_RAG_DIR, chunks, tax_rag

FIRST_STAGE_K = 50     # candidates reranked, as on the legal benchmarks (RERANK_TOP)
FETCH = 40             # ranked chunks scored, as in the teammate's scripts/evaluate.py
RERANKERS = {"bge-reranker-v2-m3": "BAAI/bge-reranker-v2-m3", "minilm-l6": "cross-encoder/ms-marco-MiniLM-L-6-v2",
             "minilm-onnx-int8": "cross-encoder/ms-marco-MiniLM-L-6-v2:onnx/model_quint8_avx2.onnx"}
INTEGRATION = ROOT / "integrations" / "bc3415-tax-rag"

# name -> first-stage config (the teammate's CONFIGS key), local embedder, reranker, contextual chunks
CONDITIONS: dict[str, dict] = {
    # the teammate's rows; dense rows use BGE-M3 where his app uses Gemini (his BM25 rows are exact)
    "naive_bm25": dict(first="naive_bm25"),
    "structured_bm25": dict(first="structured_bm25"),
    "structured_bm25_boost": dict(first="structured_bm25_boost"),
    "naive_dense@bge-m3": dict(first="naive_dense"),
    "structured_dense@bge-m3": dict(first="structured_dense"),
    "structured_hybrid@bge-m3": dict(first="structured_hybrid"),
    "structured_hybrid_boost@bge-m3": dict(first="structured_hybrid_boost"),
    "structured_routed@bge-m3": dict(first="structured_routed"),
    # Experiment 3 methods
    "R4": dict(first="structured_hybrid_boost", rerank="bge-reranker-v2-m3"),
    "R4-routed": dict(first="structured_routed", rerank="bge-reranker-v2-m3"),
    "R4-bm25": dict(first="structured_bm25_boost", rerank="bge-reranker-v2-m3"),
    "R4e": dict(first="structured_hybrid_boost", rerank="bge-reranker-v2-m3", embedder="qwen3-emb-0.6b"),
    "R5": dict(first="structured_hybrid_boost", rerank="bge-reranker-v2-m3", contextual=True),
    # reranker rank fused with the first-stage rank (RRF) instead of replacing it; chosen against R4/R5 on dev
    "R4f": dict(first="structured_hybrid_boost", rerank="bge-reranker-v2-m3", fuse=True),
    "R5f": dict(first="structured_hybrid_boost", rerank="bge-reranker-v2-m3", contextual=True, fuse=True),
    # CPU-only, fits Render's free tier next to the teammate's app
    "D1": dict(first="structured_bm25_boost", rerank="minilm-l6"),
    "D2": dict(first="structured_hybrid_boost", rerank="minilm-l6", embedder="bge-small"),
    # Exactly what integrations/bc3415-tax-rag ships: the int8 ONNX MiniLM on CPU, top 20, 256 tokens, fused.
    # D1i is the teammate's no-key fallback (BM25 + boost) plus the reranker; D3i@gemini his `improved` plus it.
    "D1i": dict(first="structured_bm25_boost", rerank="minilm-onnx-int8", rerank_top=20, max_length=256, fuse=True),
    # The teammate's own Gemini index (committed in his repo) + our reranker: needs GEMINI_API_KEY for the
    # query vectors only. Skipped, and reported as pending, without a key.
    "naive_dense@gemini": dict(first="naive_dense", embedder="gemini"),
    "structured_dense@gemini": dict(first="structured_dense", embedder="gemini"),
    "structured_hybrid@gemini": dict(first="structured_hybrid", embedder="gemini"),
    "structured_routed@gemini": dict(first="structured_routed", embedder="gemini"),
    "structured_hybrid_boost@gemini": dict(first="structured_hybrid_boost", embedder="gemini"),
    "R4@gemini": dict(first="structured_hybrid_boost", rerank="bge-reranker-v2-m3", embedder="gemini"),
    "R4-routed@gemini": dict(first="structured_routed", rerank="bge-reranker-v2-m3", embedder="gemini"),
    "R4f@gemini": dict(first="structured_hybrid_boost", rerank="bge-reranker-v2-m3", fuse=True, embedder="gemini"),
    "D3@gemini": dict(first="structured_routed", rerank="minilm-l6", embedder="gemini"),
    "D3i@gemini": dict(first="structured_routed", rerank="minilm-onnx-int8", rerank_top=20, max_length=256, fuse=True, embedder="gemini"),
}
NEEDS_KEY = {name for name, spec in CONDITIONS.items() if spec.get("embedder") == "gemini"}


class LocalDense:
    """Stands in for the teammate's DenseIndex (Chroma): exact cosine search over a matrix."""

    def __init__(self, ids: list[str], matrix: np.ndarray):
        self.ids, self.matrix = ids, matrix

    def count(self) -> int:
        return len(self.ids)

    def search(self, vector, k: int = 10) -> list[tuple[str, float]]:
        scores = self.matrix @ np.asarray(vector, dtype=np.float32)
        top = np.argsort(-scores)[:k]
        return [(self.ids[i], float(scores[i])) for i in top]


class QueryEmbedder:
    """The teammate's Embedder protocol, backed by a local sentence-transformers model (queries cached)."""

    def __init__(self, embedder: Embedder):
        self.embedder, self.name, self._vectors = embedder, f"local:{embedder.key}", {}

    def prepare(self, queries: list[str]) -> None:
        todo = [q for q in dict.fromkeys(queries) if q not in self._vectors]
        if todo:
            for q, v in zip(todo, self.embedder.encode_queries(todo)):
                self._vectors[q] = v

    def embed_query(self, text: str):
        if text not in self._vectors:
            self.prepare([text])
        return self._vectors[text]

    def embed_documents(self, texts):
        raise NotImplementedError("documents are embedded once, in TaxSearch")


class TaxSearch:
    """The teammate's retriever over one chunk text variant (plain `embed_text()` or contextual) and embedder."""

    def __init__(self, embedder: str = "bge-m3", contexts: dict[str, str] | None = None, embedders: dict | None = None):
        rag = tax_rag()
        self.contexts = contexts
        if embedder == "gemini":
            self._init_gemini(rag)
            return
        embedders = embedders if embedders is not None else {}
        if embedder not in embedders:
            embedders[embedder] = Embedder(embedder)
        self.emb = embedders[embedder]
        self.query_embedder = QueryEmbedder(self.emb)
        self.retriever = rag.retrieve.Retriever(TAX_RAG_DIR / "index", self.query_embedder)
        self.doc_vectors: dict[str, np.ndarray] = {}
        for name in ("structured", "naive"):
            if name == "naive" and contexts is not None:
                continue   # contextual chunks exist for the structured corpus only
            corpus = rag.retrieve.Corpus.load(TAX_RAG_DIR / "index", name)
            rows = chunks(name)
            texts = [self.text(c) for c in rows]
            if contexts is not None:   # BM25 over the contextual texts too, as in Experiment 3 R5
                corpus = rag.retrieve.Corpus(name, rows, rag.bm25.BM25Index.build([c.chunk_id for c in rows], texts))
            matrix = self.emb.encode_docs(texts)
            corpus.dense = LocalDense([c.chunk_id for c in rows], matrix)
            self.retriever._corpora[name] = corpus
            if name == "structured":
                self.doc_vectors = {c.chunk_id: matrix[i] for i, c in enumerate(rows)}

    def _init_gemini(self, rag) -> None:
        """The teammate's own dense index: his Chroma collections of Gemini vectors, his embedder for queries."""
        if self.contexts is not None:
            raise ValueError("contextual chunks would need a new Gemini document index; not built")
        from src.common import CACHE
        self.emb = None
        self.query_embedder = rag.embed.CachedEmbedder(rag.embed.GeminiEmbedder(), CACHE / "tax" / "gemini-query-vectors.json")
        self.retriever = rag.retrieve.Retriever(TAX_RAG_DIR / "index", self.query_embedder)
        for name in ("structured", "naive"):
            corpus = self.retriever.corpus(name, dense=True)   # his Chroma collection (checked complete)
            got = corpus.dense.collection.get(include=["embeddings"])
            vectors = dict(zip(got["ids"], got["embeddings"]))
            rows = chunks(name)
            # Exact search over his stored vectors instead of Chroma's HNSW, whose neighbours vary between process
            # starts (3 of 144 held-out questions); in chunk order, since the graph's neighbour edges break ties by it.
            matrix = np.stack([np.asarray(vectors[c.chunk_id], dtype=np.float32) for c in rows])
            matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
            corpus.dense = LocalDense([c.chunk_id for c in rows], matrix)
            if name == "structured":
                self.doc_vectors = {c.chunk_id: matrix[i] for i, c in enumerate(rows)}

    def prepare(self, queries: list[str]) -> None:
        """Embed every query up front (one batch locally; cached on disk for Gemini)."""
        if self.emb is None:
            for q in dict.fromkeys(queries):
                self.query_embedder.embed_query(q)
            return
        self.query_embedder.prepare(queries)
        self.emb.unload()   # queries and documents are embedded; free the GPU for the reranker

    def text(self, chunk) -> str:
        """What BM25, the embedder and the reranker see: the teammate's embed_text(), after the context if any."""
        base = chunk.embed_text()
        if self.contexts is None:
            return base
        return f"{self.contexts[chunk.chunk_id]}\n\n{base}"

    def first_stage(self, query: str, config: str, k: int = FIRST_STAGE_K) -> list:
        return [hit.chunk for hit in self.retriever.search(query, config, k).hits]


class IntegrationReranker:
    """The reranker as shipped in integrations/bc3415-tax-rag/rag/rerank.py (ONNX on CPU), with a score cache."""

    def __init__(self, max_length: int):
        import importlib.util
        tax_rag()   # its imports (rag.fusion, rag.schema) are the teammate's package
        spec = importlib.util.spec_from_file_location("rag.rerank", INTEGRATION / "rag" / "rerank.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.model = module.OnnxCrossEncoder(max_length=max_length)
        self.cache = JsonCache("rerank-" + self.model.name.replace("/", "_").replace(":", "_") + f"-{max_length}")

    def score(self, query: str, texts: list[str]) -> list[float]:
        key = stable_hash(query, *texts)
        hit = self.cache.get(key)
        if hit is None:
            hit = self.model.score(query, texts)
            self.cache.put(key, hit)
        return hit


def rerank(reranker, search: TaxSearch, query: str, candidates: list, fuse: bool = False,
           top: int | None = None) -> tuple[list, list[float]]:
    """The first `top` candidates (all by default) reordered by the cross-encoder (or, with `fuse`, by RRF of the
    first-stage and reranker ranks), followed by the rest in first-stage order; and the reordered scores."""
    tail = candidates[top:] if top else []
    candidates = candidates[:top] if top else candidates
    scores = reranker.score(query, [search.text(c) for c in candidates])
    order = sorted(range(len(candidates)), key=lambda i: (-scores[i], i))
    if fuse:
        fused = tax_rag().fusion.rrf([[str(i) for i in range(len(candidates))], [str(i) for i in order]])
        order = sorted(range(len(candidates)), key=lambda i: (-fused[str(i)], i))
    return [candidates[i] for i in order] + tail, [scores[i] for i in order]
