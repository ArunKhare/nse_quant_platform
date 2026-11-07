"""Tests for refusal replay reconciliation."""

from __future__ import annotations

from nse_quant.data_platform.refusal_replay_reconciliation import (
    RAN_STAGES,
    reconcile_refusal_replay,
)


def _valid_replay():
    return dict(
        replayed_stages=RAN_STAGES,
        stage_outcomes={stage: "outcome" for stage in RAN_STAGES},
    )


def test_valid_replay_reconciled():
    result = reconcile_refusal_replay(**_valid_replay())
    assert result["reconciled"] is True
    assert result["reason"] == "REFUSAL_REPLAY_RECONCILED"
    assert result["violations"] == []


def test_not_run_stage_replayed():
    candidate = _valid_replay()
    candidate["replayed_stages"] = RAN_STAGES + ("strategy",)
    result = reconcile_refusal_replay(**candidate)
    assert result["reconciled"] is False
    assert result["reason"] == "REFUSAL_REPLAY_VIOLATIONS"
    assert "NOT_RUN_STAGE_REPLAYED:strategy" in result["violations"]


def test_not_run_stage_outcome_present():
    candidate = _valid_replay()
    candidate["stage_outcomes"]["portfolio_risk"] = "outcome"
    result = reconcile_refusal_replay(**candidate)
    assert result["reconciled"] is False
    assert result["reason"] == "REFUSAL_REPLAY_VIOLATIONS"
    assert "NOT_RUN_STAGE_OUTCOME_PRESENT:portfolio_risk" in result["violations"]


def test_unknown_stage_replayed():
    candidate = _valid_replay()
    candidate["replayed_stages"] = RAN_STAGES + ("unknown_stage",)
    result = reconcile_refusal_replay(**candidate)
    assert result["reconciled"] is False
    assert result["reason"] == "REFUSAL_REPLAY_VIOLATIONS"
    assert "UNKNOWN_STAGE_REPLAYED:unknown_stage" in result["violations"]


def test_unknown_stage_outcome_present():
    candidate = _valid_replay()
    candidate["stage_outcomes"]["unknown_stage"] = "outcome"
    result = reconcile_refusal_replay(**candidate)
    assert result["reconciled"] is False
    assert result["reason"] == "REFUSAL_REPLAY_VIOLATIONS"
    assert "UNKNOWN_STAGE_OUTCOME_PRESENT:unknown_stage" in result["violations"]


def test_non_tuple_replayed_stages_refused():
    result = reconcile_refusal_replay(replayed_stages="not_a_tuple", stage_outcomes=dict())
    assert result["reconciled"] is False
    assert result["reason"] == "REPLAYED_STAGES_TUPLE_REQUIRED"
    assert "REPLAYED_STAGES_TUPLE_REQUIRED" in result["violations"]


def test_non_dict_stage_outcomes_refused():
    result = reconcile_refusal_replay(replayed_stages=RAN_STAGES, stage_outcomes="not_a_dict")
    assert result["reconciled"] is False
    assert result["reason"] == "STAGE_OUTCOMES_DICT_REQUIRED"
    assert "STAGE_OUTCOMES_DICT_REQUIRED" in result["violations"]
