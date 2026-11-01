"""TaxRAG track: the adapter reproduces the teammate's numbers, the question set is consistent, the graph is sane.

Skipped when the teammate's repo is not cloned next to this one (TAX_RAG_DIR).
"""
import json
import re
import statistics

import pytest

from src.tax.corpus import QUESTION_SETS, TAX_RAG_DIR

pytestmark = pytest.mark.skipif(not (TAX_RAG_DIR / "rag" / "retrieve.py").exists(), reason="bc3415-tax-rag not cloned")


@pytest.fixture(scope="module")
def rag():
    from src.tax.corpus import tax_rag
    return tax_rag()


def test_bm25_rows_match_the_teammates_published_numbers(rag):
    """His results/metrics.md: naive_bm25 0.44/0.46/0.44, structured_bm25 0.42/0.43/0.59 (R@5, MRR@10, R@2,500)."""
    from src.tax.corpus import load_tax_questions, spans
    retriever = rag.retrieve.Retriever(TAX_RAG_DIR / "index")
    qs = [q for q in load_tax_questions("reference") if q.answerable]
    sp = spans()
    for config, expected in {"naive_bm25": (0.44, 0.46, 0.44), "structured_bm25": (0.42, 0.43, 0.59)}.items():
        got = []
        for q in qs:
            ranked = [h.chunk for h in retriever.search(q.question, config, 40).hits]
            got.append((rag.evaluate.recall_at_k(ranked, q.gold_units, sp, 5), rag.evaluate.reciprocal_rank(ranked[:10], q.gold_units, sp),
                        rag.evaluate.recall_at_k(rag.retrieve.within_budget(ranked, 2500), q.gold_units, sp, k=len(ranked))))
        assert tuple(round(statistics.fmean(x), 2) for x in zip(*got)) == expected, config


@pytest.mark.skipif(not QUESTION_SETS["heldout"].exists(), reason="held-out set not built")
def test_heldout_questions_are_consistent(rag):
    from src.tax.corpus import chunks, load_tax_questions
    rows = chunks("structured")
    sections = {c.section for c in rows if c.doc_type == "act"}
    paras = {(c.chunk_id.split(":", 1)[0], re.sub(r"#\d+$", "", c.chunk_id.split(":", 1)[1])) for c in rows if c.doc_type == "guide"}
    qs = load_tax_questions("heldout")
    assert len({q.id for q in qs}) == len(qs)
    assert {q.split for q in qs} == {"dev", "test"}
    for q in qs:
        assert bool(q.gold_units) == q.answerable, q.id
        for doc, unit in q.gold_units:
            assert (unit in sections) if doc == "ITA" else ((doc, unit) in paras), (q.id, doc, unit)
    raw = [json.loads(line) for line in QUESTION_SETS["heldout"].read_text(encoding="utf-8").splitlines() if line.strip()]
    assert all(r["evidence"] == "" for r in raw), "IRAS evidence quotes must stay out of this public repo"


def test_graph_resolves_section_references_by_any_chunk():
    from src.tax.corpus import chunks
    from src.tax.graph import build_edges
    edges = build_edges(chunks("structured"))
    types = {e["type"] for e in edges}
    assert {"REFERS_TO", "DEFINED_IN", "CONTINUES", "INTERPRETED_BY"} <= types
    sec = [e for e in edges if e["group"].startswith("sec:")]
    assert sec and all(e["dst"].startswith("ITA:s" + e["group"][4:] + "(") or e["dst"].startswith("ITA:s" + e["group"][4:] + "#") for e in sec)
    assert all(e["src"] != e["dst"] for e in edges)
