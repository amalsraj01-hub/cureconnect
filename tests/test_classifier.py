"""Tests for the confidence gate.

These are pure-function tests: they never load app/model.joblib, so they stay
fast and cannot be broken by a retrain.
"""
import pytest

from app.classifier import (
    CONFIDENCE_THRESHOLD,
    MARGIN_THRESHOLD,
    is_low_confidence,
    top_conditions,
    top_two_margin,
)
from app.mapping import DEFAULT_SPECIALIST


def _ranked(*probabilities):
    """Build a ranking, most likely first, in the shape ranked_predictions()
    returns it: [(condition, probability), ...]."""
    return [(f"condition{index}", probability)
            for index, probability in enumerate(probabilities, start=1)]


def test_margin_is_the_gap_to_the_runner_up():
    assert top_two_margin(_ranked(0.60, 0.25, 0.10)) == pytest.approx(0.35)


def test_margin_with_a_single_candidate_is_the_whole_probability():
    # A degenerate model must not crash the API just because there is no
    # second place to compare against.
    assert top_two_margin(_ranked(0.42)) == pytest.approx(0.42)


def test_clear_winner_above_the_threshold_is_shown():
    assert not is_low_confidence(_ranked(0.60, 0.10))


def test_weak_winner_is_hidden_even_when_nothing_is_close():
    assert is_low_confidence(_ranked(0.04, 0.00))


def test_confident_score_with_a_tied_runner_up_is_still_hidden():
    # Hepatitis B/C/D/E score almost identically, so a "confident looking"
    # 0.31 vs 0.30 is really a coin flip. Confidence alone would show it.
    tied = _ranked(CONFIDENCE_THRESHOLD + 2 * MARGIN_THRESHOLD,
                   CONFIDENCE_THRESHOLD + MARGIN_THRESHOLD)
    assert tied[0][1] > CONFIDENCE_THRESHOLD
    assert is_low_confidence(tied)


def test_margin_can_only_add_fallbacks_never_remove_them():
    # The margin is a veto used alongside confidence, not a replacement for
    # it: every ranking confidence already hid must stay hidden.
    for probabilities in [(0.02, 0.00), (0.10, 0.09), (0.31, 0.30), (0.60, 0.10)]:
        ranked = _ranked(*probabilities)
        if ranked[0][1] < CONFIDENCE_THRESHOLD:
            assert is_low_confidence(ranked)


def test_configured_thresholds_are_sane():
    assert 0.0 < CONFIDENCE_THRESHOLD < 0.5
    # A margin as wide as the threshold would hide almost everything, which
    # would make the threshold itself pointless.
    assert 0.0 < MARGIN_THRESHOLD < CONFIDENCE_THRESHOLD


def test_top_conditions_carries_the_specialist_of_each_alternative():
    """The frontend renders these when the gate answers "Unclear".

    Each entry has to carry its own specialist: that answer tells the user to
    start with a General Physician, while "Diabetes" sitting in the same list
    means an Endocrinologist. The browser must not keep a second copy of
    app/mapping.py to work that out, so the API sends it.
    """
    ranked = [("Diabetes", 0.31), ("Hepatitis B", 0.12), ("Hypothyroidism", 0.05)]
    top = top_conditions(ranked)
    assert [entry["condition"] for entry in top] == [
        "Diabetes", "Hepatitis B", "Hypothyroidism"]
    assert [entry["specialist"] for entry in top] == [
        "Endocrinologist", "Gastroenterologist", "Endocrinologist"]
    assert [entry["confidence"] for entry in top] == [0.31, 0.12, 0.05]


def test_top_conditions_returns_three_best_first():
    ranked = [(f"condition{index}", 1.0 - index / 10) for index in range(5)]
    top = top_conditions(ranked)
    assert len(top) == 3
    assert [entry["confidence"] for entry in top] == [1.0, 0.9, 0.8]


def test_top_conditions_tolerates_a_short_ranking():
    # A degenerate model that only ever predicts one class must still produce a
    # usable payload instead of raising.
    top = top_conditions([("condition1", 0.4)])
    assert len(top) == 1
    assert top[0]["condition"] == "condition1"


def test_top_conditions_falls_back_for_a_condition_missing_from_the_table():
    # The specialist table is hand-written and can fall behind the model; an
    # unmapped condition must still suggest a doctor rather than a blank.
    top = top_conditions([("Not A Real Condition", 0.5)])
    assert top[0]["specialist"] == DEFAULT_SPECIALIST
