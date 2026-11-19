"""Tests for native execution-stage refusal record."""

from __future__ import annotations

import pytest

from nse_quant.data_platform.native_execution_refusal import (
    EXECUTION_STAGE,
    NOT_RUN,
    execution_refusal_record,
)


def _refusal_decision():
    return dict(
        stages={
            "kill_switch": {"status": "PASSED"},
            "safety_boundary": {"status": "PASSED"},
            "publication_admission": {"status": "REFUSED", "reason": "research_only"},
            "native_inputs": {"status": "NOT_RUN"},
            "strategy": {"status": "NOT_RUN"},
            "portfolio_risk": {"status": "NOT_RUN"},
        }
    )


def test_execution_stage_added():
    result = execution_refusal_record(refusal_decision=_refusal_decision())
    assert EXECUTION_STAGE in result["stages"]
    assert result["stages"][EXECUTION_STAGE]["status"] == NOT_RUN
    assert result["stages"][EXECUTION_STAGE]["reason"] == "execution_not_authorized"


def test_original_stages_preserved():
    original = _refusal_decision()
    result = execution_refusal_record(refusal_decision=original)
    for stage in original["stages"]:
        assert result["stages"][stage] == original["stages"][stage]


def test_execution_already_recorded_refused():
    decision = _refusal_decision()
    decision["stages"][EXECUTION_STAGE] = {"status": "RAN"}
    with pytest.raises(ValueError, match="ALREADY_RECORDED"):
        execution_refusal_record(refusal_decision=decision)


def test_missing_stages_refused():
    with pytest.raises(ValueError, match="STAGES_REQUIRED"):
        execution_refusal_record(refusal_decision=dict())


def test_non_dict_refused():
    with pytest.raises(ValueError, match="OBJECT_REQUIRED"):
        execution_refusal_record(refusal_decision="not_a_dict")
