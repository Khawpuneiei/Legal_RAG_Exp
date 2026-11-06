"""TaxRAG blind judging: how two or three grades combine, and the agreement statistic."""
from eval.tax_judge import _final, _kappa


def test_agreed_grade_wins_and_a_disagreement_takes_the_median_of_three():
    assert _final("partial", "partial", None) == "partial"
    assert _final("correct", "correct", "incorrect") == "correct"
    assert _final("correct", "incorrect", "partial") == "partial"
    assert _final("correct", "partial", "correct") == "correct"
    assert _final("incorrect", "partial", "incorrect") == "incorrect"


def test_without_a_tie_break_the_lower_grade_counts_and_a_single_grade_stands():
    assert _final("correct", "incorrect", None) == "incorrect"
    assert _final(None, "correct", None) == "correct"


def test_kappa_is_one_for_perfect_agreement_and_zero_for_chance():
    assert _kappa([("correct", "correct"), ("partial", "partial"), ("incorrect", "incorrect")]) == 1.0
    assert abs(_kappa([("correct", "correct"), ("correct", "incorrect"), ("incorrect", "correct"), ("incorrect", "incorrect")])) < 1e-12
