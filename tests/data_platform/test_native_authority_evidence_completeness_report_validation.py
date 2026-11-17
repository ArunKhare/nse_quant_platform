"""Tests for native authority evidence completeness report validation and audit integration."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from nse_quant.data_platform.native_authority_evidence_completeness_report_validation import (
    validate_authority_evidence_completeness_report,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-validation@1"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _round_tripped(kind: str) -> dict[str, Any]:
    report = {
        "complete": True,
        "version": VERSION,
        "evidence_kind": kind,
        "obligations": [
            "original_first_write",
            "audit",
            "orphan_check",
            "final_audit",
        ],
        "missing_obligations": [],
        "audit_integrated": True,
        "orphan_check_integrated": True,
        "final_audit_integrated": True,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "version": VERSION,
        "report": report,
        "round_trip_fingerprint": hashlib.sha256(_canonical_bytes(report)).hexdigest(),
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def test_validates_identity_time_completeness_report() -> None:
    result = validate_authority_evidence_completeness_report(_round_tripped("identity_time"))
    assert result["validated"] is True
    assert result["complete"] is True
    assert result["report"]["evidence_kind"] == "identity_time"
    assert result["audit_integrated"] is True
    assert result["orphan_check_integrated"] is True
    assert result["final_audit_integrated"] is True
    assert result["decision_eligibility_asserted"] is False


def test_validates_availability_completeness_report() -> None:
    result = validate_authority_evidence_completeness_report(_round_tripped("availability"))
    assert result["validated"] is True
    assert result["complete"] is True
    assert result["report"]["evidence_kind"] == "availability"
    assert result["decision_eligibility_asserted"] is False


def test_validates_economic_validity_completeness_report() -> None:
    result = validate_authority_evidence_completeness_report(_round_tripped("economic_validity"))
    assert result["validated"] is True
    assert result["complete"] is True
    assert result["report"]["evidence_kind"] == "economic_validity"
    assert result["decision_eligibility_asserted"] is False


def test_validates_incomplete_report() -> None:
    round_tripped = _round_tripped("identity_time")
    report = round_tripped["report"]
    assert isinstance(report, dict)
    report["obligations"].remove("final_audit")
    report["missing_obligations"] = ["final_audit"]
    report["final_audit_integrated"] = False
    round_tripped["round_trip_fingerprint"] = hashlib.sha256(_canonical_bytes(report)).hexdigest()
    result = validate_authority_evidence_completeness_report(round_tripped)
    assert result["validated"] is True
    assert result["complete"] is False
    assert result["missing_obligations"] == ["final_audit"]
    assert result["final_audit_integrated"] is False
    assert result["decision_eligibility_asserted"] is False


def test_rejects_fingerprint_mismatch() -> None:
    round_tripped = _round_tripped("identity_time")
    round_tripped["report"]["complete"] = False
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_ROUND_TRIP_FINGERPRINT_MISMATCH"):
        validate_authority_evidence_completeness_report(round_tripped)


def test_rejects_point_in_time_decision() -> None:
    round_tripped = _round_tripped("identity_time")
    round_tripped["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        validate_authority_evidence_completeness_report(round_tripped)


def test_rejects_healing() -> None:
    round_tripped = _round_tripped("identity_time")
    round_tripped["report"]["healed"] = True
    round_tripped["round_trip_fingerprint"] = hashlib.sha256(_canonical_bytes(round_tripped["report"])).hexdigest()
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"):
        validate_authority_evidence_completeness_report(round_tripped)
