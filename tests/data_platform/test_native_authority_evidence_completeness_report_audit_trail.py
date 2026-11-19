"""Tests for native authority evidence completeness report audit trail and reconciliation integration."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from nse_quant.data_platform.native_authority_evidence_completeness_report_audit_trail import (
    build_authority_evidence_completeness_report_audit_trail,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-audit-trail@1"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _reconciled(kind: str) -> dict[str, Any]:
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
    envelope = {
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
        "reconciled": envelope,
        "reconciliation_fingerprint": hashlib.sha256(_canonical_bytes(envelope)).hexdigest(),
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def test_builds_identity_time_audit_trail() -> None:
    result = build_authority_evidence_completeness_report_audit_trail(_reconciled("identity_time"))
    audit_trail = result["audit_trail"]
    assert isinstance(audit_trail, dict)
    assert result["audit_trail_built"] is True
    assert audit_trail["complete"] is True
    assert audit_trail["report"]["evidence_kind"] == "identity_time"
    assert audit_trail["audit_integrated"] is True
    assert audit_trail["orphan_check_integrated"] is True
    assert audit_trail["final_audit_integrated"] is True
    assert result["decision_eligibility_asserted"] is False


def test_builds_availability_audit_trail() -> None:
    result = build_authority_evidence_completeness_report_audit_trail(_reconciled("availability"))
    audit_trail = result["audit_trail"]
    assert isinstance(audit_trail, dict)
    assert audit_trail["complete"] is True
    assert audit_trail["report"]["evidence_kind"] == "availability"
    assert result["decision_eligibility_asserted"] is False


def test_builds_economic_validity_audit_trail() -> None:
    result = build_authority_evidence_completeness_report_audit_trail(_reconciled("economic_validity"))
    audit_trail = result["audit_trail"]
    assert isinstance(audit_trail, dict)
    assert audit_trail["complete"] is True
    assert audit_trail["report"]["evidence_kind"] == "economic_validity"
    assert result["decision_eligibility_asserted"] is False


def test_builds_incomplete_audit_trail() -> None:
    reconciled = _reconciled("identity_time")
    envelope = reconciled["reconciled"]
    assert isinstance(envelope, dict)
    report = envelope["report"]
    assert isinstance(report, dict)
    report["obligations"].remove("final_audit")
    report["missing_obligations"] = ["final_audit"]
    report["final_audit_integrated"] = False
    envelope["complete"] = False
    envelope["missing_obligations"] = ["final_audit"]
    envelope["final_audit_integrated"] = False
    reconciled["reconciliation_fingerprint"] = hashlib.sha256(_canonical_bytes(envelope)).hexdigest()
    result = build_authority_evidence_completeness_report_audit_trail(reconciled)
    audit_trail = result["audit_trail"]
    assert isinstance(audit_trail, dict)
    assert audit_trail["complete"] is False
    assert audit_trail["missing_obligations"] == ["final_audit"]
    assert audit_trail["final_audit_integrated"] is False
    assert result["decision_eligibility_asserted"] is False


def test_rejects_fingerprint_mismatch() -> None:
    reconciled = _reconciled("identity_time")
    reconciled["reconciled"]["complete"] = False
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_RECONCILIATION_FINGERPRINT_MISMATCH"):
        build_authority_evidence_completeness_report_audit_trail(reconciled)


def test_rejects_point_in_time_decision() -> None:
    reconciled = _reconciled("identity_time")
    reconciled["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        build_authority_evidence_completeness_report_audit_trail(reconciled)


def test_rejects_healing() -> None:
    reconciled = _reconciled("identity_time")
    reconciled["reconciled"]["report"]["healed"] = True
    reconciled["reconciliation_fingerprint"] = hashlib.sha256(_canonical_bytes(reconciled["reconciled"])).hexdigest()
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"):
        build_authority_evidence_completeness_report_audit_trail(reconciled)
