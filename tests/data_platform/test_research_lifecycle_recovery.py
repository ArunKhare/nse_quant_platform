"""Tests for research lifecycle recovery reconciliation."""

from __future__ import annotations

from nse_quant.data_platform.research_lifecycle_recovery import (
    reconcile_lifecycle_recovery,
)


def _valid_recovery():
    return dict(
        original_obligations=dict(
            obligation_1="failed",
            obligation_2="incomplete",
            obligation_3="unlinked",
            obligation_4="orphan",
        ),
        recovery_outcomes=dict(
            obligation_1="review_required",
            obligation_2="review_required",
            obligation_3="review_required",
            obligation_4="review_required",
        ),
    )


def test_valid_recovery_reconciled():
    result = reconcile_lifecycle_recovery(**_valid_recovery())
    assert result["reconciled"] is True
    assert result["reason"] == "LIFECYCLE_RECOVERY_RECONCILED"
    assert result["violations"] == []


def test_original_obligation_healed():
    candidate = _valid_recovery()
    candidate["recovery_outcomes"]["obligation_1"] = "resolved"
    result = reconcile_lifecycle_recovery(**candidate)
    assert result["reconciled"] is False
    assert result["reason"] == "LIFECYCLE_RECOVERY_VIOLATIONS"
    assert "ORIGINAL_OBLIGATION_HEALED:obligation_1" in result["violations"]


def test_invalid_original_state():
    candidate = _valid_recovery()
    candidate["original_obligations"]["obligation_1"] = "invalid_state"
    result = reconcile_lifecycle_recovery(**candidate)
    assert result["reconciled"] is False
    assert result["reason"] == "LIFECYCLE_RECOVERY_VIOLATIONS"
    assert "INVALID_ORIGINAL_STATE:obligation_1:invalid_state" in result["violations"]


def test_empty_recovery_outcomes():
    candidate = _valid_recovery()
    candidate["recovery_outcomes"] = dict()
    result = reconcile_lifecycle_recovery(**candidate)
    assert result["reconciled"] is True
    assert result["reason"] == "LIFECYCLE_RECOVERY_RECONCILED"
    assert result["violations"] == []


def test_non_dict_original_obligations_refused():
    result = reconcile_lifecycle_recovery(
        original_obligations="not_a_dict", recovery_outcomes=dict()
    )
    assert result["reconciled"] is False
    assert result["reason"] == "ORIGINAL_OBLIGATIONS_DICT_REQUIRED"
    assert "ORIGINAL_OBLIGATIONS_DICT_REQUIRED" in result["violations"]


def test_non_dict_recovery_outcomes_refused():
    result = reconcile_lifecycle_recovery(
        original_obligations=dict(), recovery_outcomes="not_a_dict"
    )
    assert result["reconciled"] is False
    assert result["reason"] == "RECOVERY_OUTCOMES_DICT_REQUIRED"
    assert "RECOVERY_OUTCOMES_DICT_REQUIRED" in result["violations"]
