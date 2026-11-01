"""WITHDRAWN: significantly worse than his retrieval on MRR@10 (docs/taxrag-results.md); kept only to reproduce D1i and D3i.

Cross-encoder reranking of the retrieved candidates, on CPU (ported from Khawpuneiei/Legal_RAG_Exp, Experiment 3).

BM25 matches words and the dense index matches meaning, but neither reads the question and a chunk together.
A cross-encoder does: it scores each (question, chunk) pair. Its rank is merged with the first-stage rank by
RRF rather than replacing it, which kept what the first stage got right on the held-out dev split
(docs/taxrag-results.md in Legal_RAG_Exp). Its best score also tells when nothing retrieved is relevant, which
is the abstention gate in rag/retrieve.py.

Runs with onnxruntime and tokenizers, both installed with chromadb, so the app still needs no torch:
cross-encoder/ms-marco-MiniLM-L-6-v2 as an int8 ONNX file (23 MB), downloaded from Hugging Face once and
cached. Reranking the top RERANK_TOP candidates at MAX_LENGTH tokens keeps Render's free tier (0.1 CPU) usable.

    reranker = CrossEncoderReranker()
    order, scores = reranker.rerank("Can a company deduct ...?", chunks)
"""

import math
import os
from typing import Protocol

from rag.fusion import rrf
from rag.schema import Chunk

MODEL_REPO = "cross-encoder/ms-marco-MiniLM-L-6-v2"
MODEL_FILE = "onnx/model_quint8_avx2.onnx"   # int8; ranks like the fp32 file (rank correlation 0.99)
MAX_LENGTH = 256          # question + chunk tokens; structured chunks are ~80 tokens (median)
RERANK_TOP = 20           # candidates scored per question
BATCH = 10


class Scorer(Protocol):
    def score(self, query: str, texts: list[str]) -> list[float]: ...


class OnnxCrossEncoder:
    """A sentence-pair classifier exported to ONNX: one relevance logit per (query, text)."""

    def __init__(self, repo: str = MODEL_REPO, filename: str = MODEL_FILE, max_length: int = MAX_LENGTH):
        import onnxruntime
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer

        self.tokenizer = Tokenizer.from_file(hf_hub_download(repo, "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length)
        self.tokenizer.enable_padding()
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = int(os.environ.get("RERANK_THREADS", "1"))
        self.session = onnxruntime.InferenceSession(hf_hub_download(repo, filename), options,
                                                    providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.session.get_inputs()}
        self.name = f"{repo}:{filename}"

    def score(self, query: str, texts: list[str]) -> list[float]:
        import numpy as np

        scores: list[float] = []
        for start in range(0, len(texts), BATCH):
            encoded = self.tokenizer.encode_batch([(query, text) for text in texts[start:start + BATCH]])
            feed = {"input_ids": [e.ids for e in encoded], "attention_mask": [e.attention_mask for e in encoded],
                    "token_type_ids": [e.type_ids for e in encoded]}
            feed = {name: np.array(rows, dtype=np.int64) for name, rows in feed.items() if name in self.inputs}
            scores.extend(float(row[0]) for row in self.session.run(None, feed)[0])
        return scores


class CrossEncoderReranker:
    def __init__(self, scorer: Scorer | None = None, top: int = RERANK_TOP):
        self._scorer, self.top = scorer, top

    @property
    def scorer(self) -> Scorer:
        if self._scorer is None:
            self._scorer = OnnxCrossEncoder()
        return self._scorer

    def rerank(self, query: str, ranked: list[Chunk]) -> tuple[list[Chunk], list[float]]:
        """The top candidates reordered by RRF of their first-stage rank and their cross-encoder rank (the rest
        keep their order after them), and each reordered candidate's cross-encoder probability."""
        head, tail = ranked[:self.top], ranked[self.top:]
        if not head:
            return ranked, []
        logits = self.scorer.score(query, [chunk.embed_text() for chunk in head])
        ids = [chunk.chunk_id for chunk in head]
        by_score = [ids[i] for i in sorted(range(len(head)), key=lambda i: (-logits[i], i))]
        fused = rrf([ids, by_score])
        order = sorted(range(len(head)), key=lambda i: (-fused[ids[i]], i))
        return [head[i] for i in order] + tail, [1 / (1 + math.exp(-logits[i])) for i in order]
