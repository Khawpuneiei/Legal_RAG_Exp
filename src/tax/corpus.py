"""The BC3415 TaxRAG corpus, read through the teammate's own code.

Corpus: the Income Tax Act 1947 (2020 Rev. Ed., one chunk per subsection) and five IRAS e-Tax guides
(one chunk per paragraph), plus the naive 500-token baseline chunks, from
https://github.com/Saiharshaa/SGtax-rag (commit ac04f49 when this was written). Chunking, BM25, RRF,
the section boost, query routing, the 2,500-token context and the scoring functions are imported from
that repo (TAX_RAG_DIR, default ../bc3415-tax-rag), so a number computed here is computed the way the
teammate's are. Nothing from the corpus is copied into this repo: the IRAS guides forbid storing them
in a retrieval system without permission, and this repo is public.

    from src.tax.corpus import tax_rag, load_tax_questions, spans
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import fields
from functools import cache
from pathlib import Path

from src.common import DATA, ROOT

TAX_RAG_DIR = Path(os.environ.get("TAX_RAG_DIR", ROOT.parent / "bc3415-tax-rag"))
TAX_DATA = DATA / "tax"
QUESTION_SETS = {
    "reference": TAX_RAG_DIR / "eval" / "questions.jsonl",   # the teammate's 28 (25 answerable, 3 out of scope)
    "heldout": TAX_DATA / "questions_heldout.jsonl",         # ours: dev split for tuning, frozen test split
}


def tax_rag():
    """The teammate's `rag` package (imported from TAX_RAG_DIR)."""
    if not (TAX_RAG_DIR / "rag" / "retrieve.py").exists():
        raise FileNotFoundError(f"clone https://github.com/Saiharshaa/SGtax-rag into {TAX_RAG_DIR} or set TAX_RAG_DIR")
    if str(TAX_RAG_DIR) not in sys.path:
        sys.path.insert(0, str(TAX_RAG_DIR))
    import rag.chunk
    import rag.evaluate
    import rag.fusion
    import rag.generate
    import rag.retrieve
    return rag


@cache
def chunks(corpus: str = "structured") -> list:
    rag = tax_rag()
    return rag.schema.load_chunks(TAX_RAG_DIR / "index" / corpus / "chunks.jsonl")


@cache
def spans() -> dict[str, dict[str, tuple[int, int]]]:
    """Gold-unit character spans per document, for scoring naive chunks by overlap.

    The teammate's build writes these to data/processed/spans.json from the parsed PDFs, which are not in git.
    They are rebuilt here from the structured chunks, which carry the same character offsets: a unit runs from
    its first chunk to the first chunk of the next unit in document order (the parser's section and paragraph
    boundaries). scripts/reproduce check: the naive BM25 row matches the teammate's published numbers.
    """
    out: dict[str, dict[str, tuple[int, int]]] = {}
    starts: dict[str, list[tuple[int, int, str]]] = {}
    for c in chunks("structured"):
        doc = c.chunk_id.split(":", 1)[0]
        unit = c.section if c.doc_type == "act" else c.chunk_id.split(":", 1)[1].split("#")[0]
        rows = starts.setdefault(doc, [])
        if not rows or rows[-1][2] != unit:
            rows.append((c.char_start, c.char_end, unit))
        else:
            s, e, u = rows[-1]
            rows[-1] = (s, max(e, c.char_end), u)
    for doc, rows in starts.items():
        units = {}
        for i, (s, e, u) in enumerate(rows):
            end = rows[i + 1][0] if i + 1 < len(rows) else e
            if u in units:          # a unit split by another (should not happen): keep the widest span
                s, end = min(s, units[u][0]), max(end, units[u][1])
            units[u] = (s, max(e, end))
        out[doc] = units
    return out


def load_tax_questions(name: str = "reference", split: str | None = None) -> list:
    """Questions as the teammate's `Question` objects. Held-out questions also carry `.split` (dev | test)."""
    rag = tax_rag()
    keep = {f.name for f in fields(rag.evaluate.Question)}
    out = []
    with open(QUESTION_SETS[name], encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            q = rag.evaluate.Question(**{k: v for k, v in row.items() if k in keep})
            q.split = row.get("split", "reference")
            if split is None or q.split == split:
                out.append(q)
    return out


def tax_commit() -> str:
    head = TAX_RAG_DIR / ".git" / "HEAD"
    try:
        ref = head.read_text().strip()
        if ref.startswith("ref: "):
            return (TAX_RAG_DIR / ".git" / ref[5:]).read_text().strip()[:7]
        return ref[:7]
    except OSError:
        return "unknown"
