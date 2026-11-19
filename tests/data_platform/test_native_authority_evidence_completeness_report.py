"""Tests for native authority evidence completeness report and audit integration."""

from __future__ import annotations

import pytest

from nse_quant.data_platform.native_authority_evidence_completeness_report import (
    build_authority_evidence_completeness_report,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _document(kind: str) -> dict[str, object]:
    return {
        "version": "native-authority-evidence-completeness-report@1",
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


def test_builds_identity_time_completeness_report() -> None:
    result = build_authority_evidence_completeness_report(_document("identity_time"))
    assert result["complete"] is True
    assert result["evidence_kind"] == "identity_time"
    assert result["audit_integrated"] is True
    assert result["orphan_check_integrated"] is True
    assert result["final_audit_integrated"] is True
    assert result["decision_eligibility_asserted"] is False


def test_builds_availability_completeness_report() -> None:
    result = build_authority_evidence_completeness_report(_document("availability"))
    assert result["complete"] is True
    assert result["evidence_kind"] == "availability"
    assert result["decision_eligibility_asserted"] is False


def test_builds_economic_validity_completeness_report() -> None:
    result = build_authority_evidence_completeness_report(_document("economic_validity"))
    assert result["complete"] is True
    assert result["evidence_kind"] == "economic_validity"
    assert result["decision_eligibility_asserted"] is False


def test_reports_missing_final_audit() -> None:
    document = _document("identity_time")
    obligations = document["obligations"]
    assert isinstance(obligations, list)
    obligations.remove("final_audit")
    result = build_authority_evidence_completeness_report(document)
    assert result["complete"] is False
    assert result["missing_obligations"] == ["final_audit"]
    assert result["final_audit_integrated"] is False
    assert result["decision_eligibility_asserted"] is False


def test_rejects_point_in_time_decision() -> None:
    document = _document("identity_time")
    document["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        build_authority_evidence_completeness_report(document)


def test_rejects_healing() -> None:
    document = _document("identity_time")
    document["healed"] = True
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"):
        build_authority_evidence_completeness_report(document)


def test_rejects_duplicate_obligations() -> None:
    document = _document("identity_time")
    obligations = document["obligations"]
    assert isinstance(obligations, list)
    obligations.append("audit")
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_OBLIGATIONS_DUPLICATE"):
        build_authority_evidence_completeness_report(document)
