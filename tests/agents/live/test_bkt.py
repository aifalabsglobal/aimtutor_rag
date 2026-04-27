"""Bayesian Knowledge Tracing helpers — pure-function tests."""

from __future__ import annotations

import pytest

from deeptutor.agents.live.bkt import (
    DEFAULT_MASTERY,
    DEFAULT_SKILL,
    bkt_update,
    infer_correctness,
    topic_to_skill,
)


@pytest.mark.parametrize(
    "prior",
    [0.0, 0.1, 0.25, 0.5, 0.75, 1.0],
)
def test_bkt_update_stays_in_unit_interval(prior: float) -> None:
    for is_correct in (True, False):
        posterior = bkt_update(prior, is_correct)
        assert 0.0 <= posterior <= 1.0


def test_bkt_correct_answer_raises_mastery() -> None:
    assert bkt_update(0.25, True) > 0.25


def test_bkt_correct_dominates_incorrect() -> None:
    assert bkt_update(0.5, True) > bkt_update(0.5, False)


def test_bkt_handles_out_of_range_prior() -> None:
    assert 0.0 <= bkt_update(-0.5, True) <= 1.0
    assert 0.0 <= bkt_update(1.5, False) <= 1.0


def test_infer_correctness_affirmation() -> None:
    assert infer_correctness("Exactly! Well done.") is True


def test_infer_correctness_correction() -> None:
    assert infer_correctness("Actually, that is incorrect.") is False


def test_infer_correctness_empty_defaults_to_true() -> None:
    assert infer_correctness("") is True


def test_topic_to_skill_normalizes_whitespace_and_punctuation() -> None:
    assert topic_to_skill("Linear Algebra") == "linear_algebra"
    assert topic_to_skill("  Photosynthesis!  ") == "photosynthesis"
    assert topic_to_skill("AP Bio: Cell Structure") == "ap_bio_cell_structure"


def test_topic_to_skill_falls_back_to_default() -> None:
    assert topic_to_skill("") == DEFAULT_SKILL
    assert topic_to_skill("   ") == DEFAULT_SKILL
    assert topic_to_skill("!!!") == DEFAULT_SKILL


def test_default_mastery_in_unit_interval() -> None:
    assert 0.0 < DEFAULT_MASTERY < 1.0
