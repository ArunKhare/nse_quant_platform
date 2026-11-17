"""Tests for native authority evidence completeness report acceptance and audit integration."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from nse_quant.data_platform.native_authority_evidence_completeness_report_acceptance import (
    accept_authority_evidence_completeness_report,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-acceptance@1"


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
    return {
        "version": VERSION,
        "report": report,
        "round_trip_fingerprint": hashlib.sha256(_canonical_bytes(report)).hexdigest(),
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def test_accepts_identity_time_completeness_report() -> None:
    result = accept_authority_evidence_completeness_report(_validated("identity_time"))
    accepted = result["accepted"]
    assert isinstance(accepted, dict)
    assert result["accepted"] is not True
    assert accepted["complete"] is True
    assert accepted["report"]["evidence_kind"] == "identity_time"
    assert accepted["audit_integrated"] is True
    assert accepted["orphan_check_integrated"] is True
    assert accepted["final_audit_integrated"] is True
    assert result["decision_eligibility_asserted"] is False


def test_accepts_availability_completeness_report() -> None:
    result = accept_authority_evidence_completeness_report(_validated("availability"))
    accepted = result["accepted"]
    assert isinstance(accepted, dict)
    assert accepted["complete"] is True
    assert accepted["report"]["evidence_kind"] == "availability"
    assert result["decision_eligibility_asserted"] is False


def test_accepts_economic_validity_completeness_report() -> None:
    result = accept_authority_evidence_completeness_report(_validated("economic_validity"))
    accepted = result["accepted"]
    assert isinstance(accepted, dict)
    assert accepted["complete"] is True
    assert accepted["report"]["evidence_kind"] == "economic_validity"
    assert result["decision_eligibility_asserted"] is False


def test_accepts_incomplete_report() -> None:
    validated = _validated("identity_time")
    report = validated["report"]
    assert isinstance(report, dict)
    report["obligations"].remove("final_audit")
    report["missing_obligations"] = ["final_audit"]
    report["final_audit_integrated"] = False
    validated["round_trip_fingerprint"] = hashlib.sha256(_canonical_bytes(report)).hexdigest()
    result = accept_authority_evidence_completeness_report(validated)
    accepted = result["accepted"]
    assert isinstance(accepted, dict)
    assert accepted["complete"] is False
    assert accepted["missing_obligations"] == ["final_audit"]
    assert accepted["final_audit_integrated"] is False
    assert result["decision_eligibility_asserted"] is False


def test_rejects_fingerprint_mismatch() -> None:
    validated = _validated("identity_time")
    validated["report"]["complete"] = False
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_ROUND_TRIP_FINGERPRINT_MISMATCH"):
        accept_authority_evidence_completeness_report(validated)


def test_rejects_point_in_time_decision() -> None:
    validated = _validated("identity_time")
    validated["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        accept_authority_evidence_completeness_report(validated)


def test_rejects_healing() -> None:
    validated = _validated("identity_time")
    validated["report"]["healed"] = True
    validated["round_trip_fingerprint"] = hashlib.sha256(_canonical_bytes(validated["report"])).hexdigest()
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"):
        accept_authority_evidence_completeness_report(validated)
