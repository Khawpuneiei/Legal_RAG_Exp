import json
from pathlib import Path

from src.common import load_synthetic

ROOT = Path(__file__).resolve().parents[1]


def test_spans_point_at_clause_text():
    ds = load_synthetic()
    clauses = ds.meta["clauses"]
    for u in ds.units:
        if u.unit_id == "DEF-MANAGEMENT-FEE":  # rendered per template (template-specific cross-reference)
            continue
        assert ds.documents[u.doc_id][u.start:u.end] == clauses[u.unit_id]["text"]


def test_gold_ids_exist_and_splits():
    ds = load_synthetic()
    ids = set(ds.meta["clauses"])
    for q in ds.queries:
        assert set(q.graded) <= ids
    splits = [q.meta["split"] for q in ds.queries]
    assert splits.count("dev") == 30 and splits.count("test") == 90


def test_edges_reference_known_clauses():
    ids = {json.loads(l)["clause_id"] for l in open(ROOT / "data/synthetic/clauses.jsonl", encoding="utf-8")}
    for line in open(ROOT / "data/synthetic/edges.jsonl", encoding="utf-8"):
        e = json.loads(line)
        assert e["dst"] in ids
