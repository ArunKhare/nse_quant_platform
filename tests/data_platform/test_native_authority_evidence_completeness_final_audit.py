"""Tests for native authority evidence completeness and final-audit integration."""

from __future__ import annotations

from typing import Any

import pytest

from nse_quant.data_platform.native_authority_evidence_completeness_final_audit import (
    validate_authority_evidence_completeness,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _document(kind: str) -> dict[str, Any]:
    return {
        "version": "native-authority-evidence-completeness-final-audit@1",
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


def test_validates_identity_time_completeness() -> None:
    result = validate_authority_evidence_completeness(_document("identity_time"))
    assert result["complete"] is True
    assert result["evidence_kind"] == "identity_time"
    assert result["audit_integrated"] is True
    assert result["orphan_check_integrated"] is True
    assert result["final_audit_integrated"] is True
    assert result["decision_eligibility_asserted"] is False


def test_validates_availability_completeness() -> None:
    result = validate_authority_evidence_completeness(_document("availability"))
    assert result["complete"] is True
    assert result["evidence_kind"] == "availability"
    assert result["decision_eligibility_asserted"] is False


def test_validates_economic_validity_completeness() -> None:
    result = validate_authority_evidence_completeness(_document("economic_validity"))
    assert result["complete"] is True
    assert result["evidence_kind"] == "economic_validity"
    assert result["decision_eligibility_asserted"] is False


def test_rejects_missing_final_audit() -> None:
    document = _document("identity_time")
    document["obligations"].remove("final_audit")
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_OBLIGATIONS_MISSING_FINAL_AUDIT"):
        validate_authority_evidence_completeness(document)


def test_rejects_point_in_time_decision() -> None:
    document = _document("identity_time")
    document["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        validate_authority_evidence_completeness(document)


def test_rejects_healing() -> None:
    document = _document("identity_time")
    document["healed"] = True
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"):
        validate_authority_evidence_completeness(document)


def test_rejects_duplicate_obligations() -> None:
    document = _document("identity_time")
    document["obligations"].append("audit")
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_OBLIGATIONS_DUPLICATE"):
        validate_authority_evidence_completeness(document)
