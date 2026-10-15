"""Turn an Experiment 3 condition (configs/experiments/exp3.yaml) into rankings for a dataset."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.common import Dataset
from src.llm.ollama import OllamaLLM
from src.retrieval.bm25 import BM25Index
from src.retrieval.chunking import Chunk, make_chunks
from src.retrieval.contextual import contextualize
from src.retrieval.dense import Embedder, dense_search
from src.retrieval.hybrid import rrf
from src.retrieval.query_rewrite import rewrite_queries
from src.retrieval.rerank import Reranker

TOP_N = 100
RERANK_TOP = 50


@dataclass
class Condition:
    name: str
    chunking: str = "clause"          # fixed | clause
    retriever: str = "dense"          # dense | bm25 | hybrid
    embedder: str = "bge-m3"          # bge-m3 | qwen3-emb-0.6b
    rerank: bool = False
    query_rewrite: bool = False
    contextual: str | None = None     # None | auto (chunk_context for synthetic, doc_summary for LBR)
    graph: str | None = None          # None | bfs | ppr | astar | astar_tuned (synthetic only)
    description: str = ""
    skip: list[str] = field(default_factory=list)  # dataset names this condition does not apply to


@dataclass
class Resources:
    llm: OllamaLLM | None = None
    reranker: Reranker | None = None
    embedders: dict[str, Embedder] = field(default_factory=dict)
    _chunks: dict = field(default_factory=dict)
    _texts: dict = field(default_factory=dict)
    _queries: dict = field(default_factory=dict)

    def embedder(self, key: str) -> Embedder:
        if key not in self.embedders:
            self.embedders[key] = Embedder(key)
        return self.embedders[key]

    def get_llm(self) -> OllamaLLM:
        if self.llm is None:
            self.llm = OllamaLLM(num_ctx=8192)
        return self.llm


def contextual_mode(ds: Dataset, cond: Condition) -> str | None:
    if not cond.contextual:
        return None
    if cond.contextual != "auto":
        return cond.contextual
    return "chunk_context" if ds.name == "synthetic" else "doc_summary"


def chunks_for(ds: Dataset, cond: Condition, res: Resources) -> list[Chunk]:
    key = (ds.name, cond.chunking)
    if key not in res._chunks:
        res._chunks[key] = make_chunks(ds, cond.chunking)
    return res._chunks[key]


def texts_for(ds: Dataset, cond: Condition, res: Resources) -> list[str]:
    chunks = chunks_for(ds, cond, res)
    mode = contextual_mode(ds, cond)
    key = (ds.name, cond.chunking, mode)
    if key not in res._texts:
        res._texts[key] = [c.text for c in chunks] if mode is None else contextualize(ds, chunks, res.get_llm(), mode)
    return res._texts[key]


def queries_for(ds: Dataset, cond: Condition, res: Resources) -> list[str]:
    key = (ds.name, cond.query_rewrite)
    if key not in res._queries:
        raw = [q.text for q in ds.queries]
        res._queries[key] = rewrite_queries(raw, res.get_llm()) if cond.query_rewrite else raw
    return res._queries[key]


def precompute_llm(ds: Dataset, cond: Condition, res: Resources) -> None:
    """Run (and cache) the LLM steps a condition needs, so GPU memory can be freed before embedding."""
    if contextual_mode(ds, cond):
        texts_for(ds, cond, res)
    if cond.query_rewrite:
        queries_for(ds, cond, res)


def rank(ds: Dataset, cond: Condition, res: Resources) -> dict:
    chunks = chunks_for(ds, cond, res)
    texts = texts_for(ds, cond, res)
    queries = queries_for(ds, cond, res)
    lists: list[list[int]] = []
    if cond.retriever in ("bm25", "hybrid"):
        bm = BM25Index(texts)
        bm_lists = [[i for i, _ in bm.search(q, TOP_N)] for q in queries]
    if cond.retriever in ("dense", "hybrid"):
        emb = res.embedder(cond.embedder)
        d = emb.encode_docs(texts)
        qe = emb.encode_queries(queries)
        dn_lists = [[i for i, _ in row] for row in dense_search(qe, d, TOP_N)]
    for qi in range(len(queries)):
        if cond.retriever == "bm25":
            ranking = bm_lists[qi]
        elif cond.retriever == "dense":
            ranking = dn_lists[qi]
        else:
            ranking = [i for i, _ in rrf([bm_lists[qi], dn_lists[qi]], top_n=TOP_N)]
        if cond.rerank:
            if res.reranker is None:
                res.reranker = Reranker()
            head = ranking[:RERANK_TOP]
            scores = res.reranker.score(queries[qi], [texts[i] for i in head])
            head = [i for _, i in sorted(zip(scores, head), key=lambda x: -x[0])]
            ranking = head + ranking[RERANK_TOP:]
        lists.append(ranking)
    return dict(chunks=chunks, texts=texts, queries=queries, rankings=lists)
