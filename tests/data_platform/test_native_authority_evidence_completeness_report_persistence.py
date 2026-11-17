"""Tests for native authority evidence completeness report persistence and replay."""

from __future__ import annotations

from typing import Any

import pytest

from nse_quant.data_platform.native_authority_evidence_completeness_report_persistence import (
    persist_authority_evidence_completeness_report,
    replay_authority_evidence_completeness_report,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _document(kind: str) -> dict[str, Any]:
    return {
        "version": "native-authority-evidence-completeness-report-persistence@1",
        "evidence": {
            "kind": kind,
            "source_authority": "accepted_authority",
            "revision_id": "a" * 64,
            "recording_fingerprint": "b" * 64,
        },
        "obligations": [
            "original_first_write",
            "audit",
            "orphan_check",
            "final_audit",
        ],
        "healed": False,
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def test_persists_identity_time_completeness_report() -> None:
    result = persist_authority_evidence_completeness_report(_document("identity_time"))
    assert result["persisted"] is True
    assert result["version"] == "native-authority-evidence-completeness-report-persistence@1"
    assert result["report"]["complete"] is True
    assert result["report"]["evidence_kind"] == "identity_time"
    assert result["decision_eligibility_asserted"] is False


def test_persists_availability_completeness_report() -> None:
    result = persist_authority_evidence_completeness_report(_document("availability"))
    assert result["persisted"] is True
    assert result["report"]["complete"] is True
    assert result["report"]["evidence_kind"] == "availability"
    assert result["decision_eligibility_asserted"] is False


def test_persists_economic_validity_completeness_report() -> None:
    result = persist_authority_evidence_completeness_report(_document("economic_validity"))
    assert result["persisted"] is True
    assert result["report"]["complete"] is True
    assert result["report"]["evidence_kind"] == "economic_validity"
    assert result["decision_eligibility_asserted"] is False


def test_replays_persisted_report_exactly() -> None:
    persisted = persist_authority_evidence_completeness_report(_document("identity_time"))
    result = replay_authority_evidence_completeness_report(persisted)
    assert result["replayed"] is True
    assert result["report"] == persisted["report"]
    assert result["report_fingerprint"] == persisted["report_fingerprint"]
    assert result["decision_eligibility_asserted"] is False


def test_rejects_report_fingerprint_mismatch() -> None:
    persisted = persist_authority_evidence_completeness_report(_document("identity_time"))
    persisted["report"]["complete"] = False
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_REPORT_FINGERPRINT_MISMATCH"):
        replay_authority_evidence_completeness_report(persisted)


def test_rejects_point_in_time_decision() -> None:
    document = _document("identity_time")
    document["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        persist_authority_evidence_completeness_report(document)


def test_rejects_healing() -> None:
    document = _document("identity_time")
    document["healed"] = True
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"):
        persist_authority_evidence_completeness_report(document)
