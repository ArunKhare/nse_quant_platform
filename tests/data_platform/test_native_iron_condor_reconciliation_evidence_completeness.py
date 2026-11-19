"""Tests for reconciliation evidence-completeness validation."""

from __future__ import annotations

from typing import Any

import pytest

from nse_quant.data_platform.native_iron_condor_reconciliation_evidence_completeness import (
    validate_reconciliation_evidence_completeness,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _reconciliation() -> dict[str, Any]:
    return {
        "authoritative_boundary": {"run_id": "run-1"},
        "authoritative_boundary_context": "a" * 64,
        "coverage_evidence_links_context": "b" * 64,
        "stages": [
            {
                "stage": "strategy",
                "replayed": True,
                "decision_eligibility_asserted": False,
            },
            {
                "stage": "portfolio_risk",
                "replayed": True,
                "decision_eligibility_asserted": False,
            },
        ],
        "complete": False,
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def test_validates_complete_evidence() -> None:
    result = validate_reconciliation_evidence_completeness(_reconciliation())
    assert result["complete_evidence"] is True
    assert result["stage_count"] == 2
    assert result["authoritative_boundary_present"] is True
    assert result["coverage_evidence_links_present"] is True
    assert result["decision_eligibility_asserted"] is False


def test_point_in_time_decision_rejected() -> None:
    reconciliation = _reconciliation()
    reconciliation["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        validate_reconciliation_evidence_completeness(reconciliation)


def test_missing_boundary_context_rejected() -> None:
    reconciliation = _reconciliation()
    del reconciliation["authoritative_boundary_context"]
    with pytest.raises(Rejected, match="AUTHORITATIVE_BOUNDARY_CONTEXT_MISSING"):
        validate_reconciliation_evidence_completeness(reconciliation)


def test_missing_evidence_context_rejected() -> None:
    reconciliation = _reconciliation()
    del reconciliation["coverage_evidence_links_context"]
    with pytest.raises(Rejected, match="COVERAGE_EVIDENCE_LINKS_CONTEXT_MISSING"):
        validate_reconciliation_evidence_completeness(reconciliation)


def test_unreplayed_stage_rejected() -> None:
    reconciliation = _reconciliation()
    reconciliation["stages"][1]["replayed"] = False
    with pytest.raises(Rejected, match="RECONCILIATION_STAGE_REPLAY_INCOMPLETE"):
        validate_reconciliation_evidence_completeness(reconciliation)
