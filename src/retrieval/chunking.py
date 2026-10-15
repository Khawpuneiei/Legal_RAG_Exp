"""Chunking strategies (plan R1 vs R2)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.common import Dataset


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    start: int
    end: int
    text: str


def fixed_chunks(ds: Dataset, size_chars: int = 2000) -> list[Chunk]:
    """R1 naive chunking: fixed windows of ~512 tokens (2,000 characters at ~4 chars/token), no overlap,
    ignoring clause boundaries."""
    out = []
    for doc_id, text in ds.documents.items():
        for i, s in enumerate(range(0, len(text), size_chars)):
            out.append(Chunk(f"{doc_id}#f{i}", doc_id, s, min(s + size_chars, len(text)), text[s:s + size_chars]))
    return out


def unit_chunks(ds: Dataset) -> list[Chunk]:
    """R2 clause-level chunking where clause boundaries are known (synthetic library, ACORD clauses).
    Splitting by clause heading keeps the heading with its clause, so the clause title is prepended to
    the chunk text; the character span still covers only the clause body."""
    titles = {cid: c["title"] for cid, c in ds.meta.get("clauses", {}).items()}
    out = []
    for i, u in enumerate(ds.units):
        body = ds.documents[u.doc_id][u.start:u.end]
        text = f"{titles[u.unit_id]}\n{body}" if u.unit_id in titles else body
        out.append(Chunk(f"{u.doc_id}#u{i}", u.doc_id, u.start, u.end, text))
    return out


_SEPARATORS = ["\n\n", "\n", ". ", "; ", ", ", " "]


def _recursive_split(text: str, start: int, max_chars: int, seps: list[str]) -> list[tuple[int, int]]:
    if len(text) <= max_chars:
        return [(start, start + len(text))] if text.strip() else []
    for sep in seps:
        if sep in text:
            pieces, pos = [], 0
            for m in re.finditer(re.escape(sep), text):
                pieces.append((pos, m.end()))
                pos = m.end()
            pieces.append((pos, len(text)))
            # greedily merge pieces up to max_chars
            out, cur_s, cur_e = [], None, None
            for s, e in pieces:
                if cur_s is None:
                    cur_s, cur_e = s, e
                elif e - cur_s <= max_chars:
                    cur_e = e
                else:
                    out.append((cur_s, cur_e))
                    cur_s, cur_e = s, e
            if cur_s is not None:
                out.append((cur_s, cur_e))
            result = []
            for s, e in out:
                if e - s > max_chars:
                    result += _recursive_split(text[s:e], start + s, max_chars, seps[seps.index(sep) + 1:])
                elif text[s:e].strip():
                    result.append((start + s, start + e))
            return result
    return [(start + i, start + min(i + max_chars, len(text))) for i in range(0, len(text), max_chars)]


def recursive_chunks(ds: Dataset, max_chars: int = 500) -> list[Chunk]:
    """Structure-aware chunking for documents without clause labels (LegalBench-RAG): split on
    paragraphs, then lines, sentences and words, merging up to max_chars (the setting used by
    LegalBench-RAG and Summary-Augmented Chunking)."""
    out = []
    for doc_id, text in ds.documents.items():
        for i, (s, e) in enumerate(_recursive_split(text, 0, max_chars, _SEPARATORS)):
            out.append(Chunk(f"{doc_id}#r{i}", doc_id, s, e, text[s:e]))
    return out


def make_chunks(ds: Dataset, strategy: str) -> list[Chunk]:
    if strategy == "fixed":
        return fixed_chunks(ds)
    if strategy == "clause":
        return unit_chunks(ds) if ds.units else recursive_chunks(ds)
    raise ValueError(strategy)
