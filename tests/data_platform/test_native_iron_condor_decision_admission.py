"""Tests for the native iron-condor decision admission contract."""

from __future__ import annotations

from typing import Any

import pytest

from nse_quant.data_platform.native_iron_condor_decision_admission import (
    evaluate_native_iron_condor_decision_admission,
)
from nse_quant.data_platform.native_iron_condor_decision_gold import (
    gold_context,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected
from nse_quant.data_platform.native_strategy_requirements import STRATEGY


def _reconciliation() -> dict[str, object]:
    return {
        "authoritative_boundary": {"run_id": "admission-run-1"},
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


def _gold() -> dict[str, Any]:
    return {
        "version": "native-iron-condor-decision-gold@1",
        "strategy": STRATEGY,
        "run_id": "admission-run-1",
        "reconciliation_revision_id": "a" * 64,
        "reconciliation_recording_fingerprint": "b" * 64,
        "identity_time_evidence_revision_id": "c" * 64,
        "identity_time_evidence_recording_fingerprint": "d" * 64,
        "availability_economic_evidence_revision_id": "e" * 64,
        "availability_economic_evidence_recording_fingerprint": "f" * 64,
        "coverage_revision_id": "a" * 64,
        "coverage_recording_fingerprint": "b" * 64,
        "coverage_evidence_links_context": "evidence-context",
        "authoritative_boundary_context": "boundary-context",
        "stages": [
            {
                "stage": "strategy",
                "replayed": True,
                "revision_id": "a" * 64,
                "recording_fingerprint": "b" * 64,
                "decision_eligibility_asserted": False,
            },
            {
                "stage": "portfolio_risk",
                "replayed": True,
                "revision_id": "c" * 64,
                "recording_fingerprint": "d" * 64,
                "decision_eligibility_asserted": False,
            },
        ],
        "complete": False,
        "decision_eligibility_asserted": False,
        "point_in_time_decision": False,
    }


def test_evaluates_admission_contract() -> None:
    gold = _gold()
    gold["context_sha256"] = gold_context(gold)
    result = evaluate_native_iron_condor_decision_admission(
        gold,
        _reconciliation(),
    )
    assert result["admission_determined"] is True
    assert result["admitted"] is False
    assert result["reason"] == "EVIDENCE_COMPLETE_ADMISSION_CONTRACT_PENDING"
    assert result["decision_eligibility_asserted"] is False
    assert result["execution_authorized"] is False


def test_point_in_time_gold_rejected() -> None:
    gold = _gold()
    gold["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        evaluate_native_iron_condor_decision_admission(
            gold,
            _reconciliation(),
        )


def test_incomplete_reconciliation_rejected() -> None:
    reconciliation = _reconciliation()
    del reconciliation["coverage_evidence_links_context"]
    with pytest.raises(Rejected, match="COVERAGE_EVIDENCE_LINKS_CONTEXT_MISSING"):
        evaluate_native_iron_condor_decision_admission(
            _gold(),
            reconciliation,
        )


def test_unreplayed_stage_rejected() -> None:
    gold = _gold()
    gold["stages"][1]["replayed"] = False
    with pytest.raises(Rejected, match="DECISION_GOLD_STAGE_REPLAY_INCOMPLETE"):
        evaluate_native_iron_condor_decision_admission(
            gold,
            _reconciliation(),
        )
