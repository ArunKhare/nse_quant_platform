"""Tests for native authority evidence completeness report audit-trail acceptance and replay integration."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from nse_quant.data_platform.native_authority_evidence_completeness_report_audit_trail_acceptance import (
    accept_authority_evidence_completeness_report_audit_trail,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-audit-trail-acceptance@1"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _validated(kind: str) -> dict[str, Any]:
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
    audit_trail = {
        "version": VERSION,
        "report": report,
        "complete": True,
        "missing_obligations": [],
        "audit_integrated": True,
        "orphan_check_integrated": True,
        "final_audit_integrated": True,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "version": VERSION,
        "audit_trail": audit_trail,
        "round_trip_fingerprint": hashlib.sha256(_canonical_bytes(audit_trail)).hexdigest(),
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def test_accepts_identity_time_audit_trail() -> None:
    result = accept_authority_evidence_completeness_report_audit_trail(_validated("identity_time"))
    assert result["acceptance_completed"] is True
    accepted = result["accepted"]
    assert isinstance(accepted, dict)
    assert accepted["complete"] is True
    assert accepted["audit_trail"]["report"]["evidence_kind"] == "identity_time"
    assert accepted["audit_integrated"] is True
    assert accepted["orphan_check_integrated"] is True
    assert accepted["final_audit_integrated"] is True
    assert result["decision_eligibility_asserted"] is False


def test_accepts_availability_audit_trail() -> None:
    result = accept_authority_evidence_completeness_report_audit_trail(_validated("availability"))
    assert result["acceptance_completed"] is True
    accepted = result["accepted"]
    assert isinstance(accepted, dict)
    assert accepted["complete"] is True
    assert accepted["audit_trail"]["report"]["evidence_kind"] == "availability"
    assert result["decision_eligibility_asserted"] is False


def test_accepts_economic_validity_audit_trail() -> None:
    result = accept_authority_evidence_completeness_report_audit_trail(_validated("economic_validity"))
    assert result["acceptance_completed"] is True
    accepted = result["accepted"]
    assert isinstance(accepted, dict)
    assert accepted["complete"] is True
    assert accepted["audit_trail"]["report"]["evidence_kind"] == "economic_validity"
    assert result["decision_eligibility_asserted"] is False


def test_accepts_incomplete_audit_trail() -> None:
    validated = _validated("identity_time")
    audit_trail = validated["audit_trail"]
    assert isinstance(audit_trail, dict)
    report = audit_trail["report"]
    assert isinstance(report, dict)
    report["obligations"].remove("final_audit")
    report["missing_obligations"] = ["final_audit"]
    report["final_audit_integrated"] = False
    audit_trail["complete"] = False
    audit_trail["missing_obligations"] = ["final_audit"]
    audit_trail["final_audit_integrated"] = False
    validated["round_trip_fingerprint"] = hashlib.sha256(_canonical_bytes(audit_trail)).hexdigest()
    result = accept_authority_evidence_completeness_report_audit_trail(validated)
    assert result["acceptance_completed"] is True
    accepted = result["accepted"]
    assert isinstance(accepted, dict)
    assert accepted["complete"] is False
    assert accepted["missing_obligations"] == ["final_audit"]
    assert accepted["final_audit_integrated"] is False
    assert result["decision_eligibility_asserted"] is False


def test_rejects_fingerprint_mismatch() -> None:
    validated = _validated("identity_time")
    validated["audit_trail"]["complete"] = False
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_ROUND_TRIP_FINGERPRINT_MISMATCH"):
        accept_authority_evidence_completeness_report_audit_trail(validated)


def test_rejects_point_in_time_decision() -> None:
    validated = _validated("identity_time")
    validated["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        accept_authority_evidence_completeness_report_audit_trail(validated)


def test_rejects_healing() -> None:
    validated = _validated("identity_time")
    validated["audit_trail"]["healed"] = True
    validated["round_trip_fingerprint"] = hashlib.sha256(_canonical_bytes(validated["audit_trail"])).hexdigest()
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"):
        accept_authority_evidence_completeness_report_audit_trail(validated)
