"""Contextual chunk enrichment before indexing (plan R5).

Two variants, chosen per dataset:
* chunk context (Anthropic "Contextual Retrieval"): an LLM writes 1-2 sentences situating each chunk
  in its document. Used for the synthetic clause library (a few hundred chunks).
* document summary (Summary-Augmented Chunking, Reuter et al. 2025): one ~150-character summary per
  document is prepended to every chunk of that document. Used for LegalBench-RAG, where per-chunk
  calls (~17k) are too slow for a local 7B model, and where SAC's evidence was gathered.
"""
from __future__ import annotations

from tqdm import tqdm

from src.common import Dataset
from src.llm.ollama import OllamaLLM
from src.retrieval.chunking import Chunk

CHUNK_PROMPT = """<document>
{doc}
</document>
Here is the chunk we want to situate within the whole document:
<chunk>
{chunk}
</chunk>
Please give a short succinct context (one or two sentences) to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else."""

SUMMARY_SYSTEM = "You are an expert legal document summarizer."
SUMMARY_PROMPT = """Summarize the following legal document text. Focus on extracting the most important entities, core purpose, and key legal topics. The summary must be concise, maximum 150 characters long, and optimized for providing context to smaller text chunks. Output only the summary text.
Document: {doc}"""


def chunk_contexts(ds: Dataset, chunks: list[Chunk], llm: OllamaLLM, max_doc_chars: int = 24000) -> list[str]:
    out = []
    for c in tqdm(chunks, desc="chunk context", disable=len(chunks) < 50):
        doc = ds.documents[c.doc_id][:max_doc_chars]
        ctx = llm.generate(CHUNK_PROMPT.format(doc=doc, chunk=c.text), max_tokens=120)["text"].strip()
        out.append(f"{ctx}\n\n{c.text}")
    return out


def doc_summaries(ds: Dataset, llm: OllamaLLM, head_chars: int = 12000, tail_chars: int = 2000) -> dict[str, str]:
    """SAC generic summary prompt. Long documents are truncated to their head and tail, since the
    local model's context is limited (SAC used the full document with gpt-4o-mini)."""
    summaries = {}
    for doc_id, text in tqdm(ds.documents.items(), desc="doc summaries"):
        doc = text if len(text) <= head_chars + tail_chars else text[:head_chars] + "\n[...]\n" + text[-tail_chars:]
        s = llm.generate(SUMMARY_PROMPT.format(doc=doc), system=SUMMARY_SYSTEM, max_tokens=80)["text"].strip()
        summaries[doc_id] = s[:170]  # SAC allowed ~20 characters of tolerance over 150
    return summaries


def contextualize(ds: Dataset, chunks: list[Chunk], llm: OllamaLLM, mode: str) -> list[str]:
    if mode == "chunk_context":
        return chunk_contexts(ds, chunks, llm)
    if mode == "doc_summary":
        summaries = doc_summaries(ds, llm)
        return [f"{summaries[c.doc_id]}\n\n{c.text}" for c in chunks]
    raise ValueError(mode)
