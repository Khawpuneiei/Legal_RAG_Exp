import math

from eval.metrics.retrieval_metrics import char_pr, ndcg_at, unit_ranking
from src.retrieval.chunking import Chunk


def test_char_pr_matches_legalbenchrag_definition():
    chunks = [Chunk("a#0", "a", 0, 100, "x" * 100), Chunk("a#1", "a", 100, 200, "x" * 100)]
    gold = [("a", 50, 150)]
    p, r = char_pr([0, 1], chunks, gold, k=1)
    assert math.isclose(p, 0.5) and math.isclose(r, 0.5)
    p, r = char_pr([0, 1], chunks, gold, k=2)
    assert math.isclose(p, 0.5) and math.isclose(r, 1.0)


def test_ndcg_perfect_and_worst():
    graded = {"u1": 3, "u2": 1}
    assert math.isclose(ndcg_at(["u1", "u2"], graded, 10), 1.0)
    assert ndcg_at(["u2", "u1"], graded, 10) < 1.0
    assert ndcg_at(["zz"], graded, 10) == 0.0


def test_ndcg_uses_linear_gains_like_pytrec_eval():
    graded = {"a": 2, "b": 1}
    # DCG = 1/log2(2) + 2/log2(3); IDCG = 2/log2(2) + 1/log2(3)
    expected = (1 + 2 / math.log2(3)) / (2 + 1 / math.log2(3))
    assert math.isclose(ndcg_at(["b", "a"], graded, 10), expected)


def test_unit_ranking_dedupes_and_keeps_first_rank():
    covers = [["u1", "u2"], ["u2"], ["u3"]]
    units, ranks = unit_ranking([1, 0, 2], covers)
    assert units == ["u2", "u1", "u3"] and ranks == [1, 2, 3]
