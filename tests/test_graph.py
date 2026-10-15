import numpy as np

from src.retrieval.graph import ClauseGraph, graph_metrics


def _toy():
    clauses = {
        "OP": dict(text="The Investor may elect to receive rights given to a Similar Investor. " * 3, variant="optional",
                   uses_terms=["DEF-SI"], refers_to=["OTHER"]),
        "DEF-SI": dict(text='"Similar Investor" means an investor of equal size.', variant="definition", uses_terms=[], refers_to=[]),
        "OTHER": dict(text="Notices shall be in writing.", variant="standard", uses_terms=[], refers_to=[]),
        "NOISE": dict(text="Unrelated clause about custody of assets.", variant="standard", uses_terms=[], refers_to=[]),
    }
    edges = [dict(src="OP", dst="DEF-SI", type="DEFINED_IN", weight=0.2), dict(src="OP", dst="OTHER", type="REFERS_TO", weight=0.3)]
    rng = np.random.default_rng(0)
    emb = {k: (lambda v: v / np.linalg.norm(v))(rng.normal(size=8)) for k in clauses}
    return clauses, edges, emb


def test_astar_resolves_dependencies_of_seed():
    clauses, edges, emb = _toy()
    g = ClauseGraph(clauses, edges, emb, knn=1)
    out = g.astar(["OP"], emb["OP"], budget=500)
    assert out["evidence"][0] == "OP"
    assert {"DEF-SI", "OTHER"} <= set(out["evidence"])
    m = graph_metrics(out["evidence"], g, {"OP": 3})
    assert m["definition_coverage"] == 1.0 and m["xref_completeness"] == 1.0


def test_budget_is_respected():
    clauses, edges, emb = _toy()
    g = ClauseGraph(clauses, edges, emb, knn=1)
    out = g.astar(["OP"], emb["OP"], budget=60)
    assert out["tokens"] <= 60
