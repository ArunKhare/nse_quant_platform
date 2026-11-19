"""Tests for native authority evidence completeness report audit-trail closure and replay integration."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from nse_quant.data_platform.native_authority_evidence_completeness_report_audit_trail_closure import (
    close_authority_evidence_completeness_report_audit_trail,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-audit-trail-closure@1"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _final_audited(kind: str) -> dict[str, Any]:
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
    envelope = {
        "version": VERSION,
        "audit_trail": audit_trail,
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
        "final_audited": envelope,
        "final_audit_fingerprint": hashlib.sha256(_canonical_bytes(envelope)).hexdigest(),
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def test_closes_identity_time_audit_trail() -> None:
    result = close_authority_evidence_completeness_report_audit_trail(_final_audited("identity_time"))
    assert result["closure_completed"] is True
    closed = result["closed"]
    assert isinstance(closed, dict)
    assert closed["complete"] is True
    assert closed["audit_trail"]["report"]["evidence_kind"] == "identity_time"
    assert closed["audit_integrated"] is True
    assert closed["orphan_check_integrated"] is True
    assert closed["final_audit_integrated"] is True
    assert result["decision_eligibility_asserted"] is False


def test_closes_availability_audit_trail() -> None:
    result = close_authority_evidence_completeness_report_audit_trail(_final_audited("availability"))
    assert result["closure_completed"] is True
    closed = result["closed"]
    assert isinstance(closed, dict)
    assert closed["complete"] is True
    assert closed["audit_trail"]["report"]["evidence_kind"] == "availability"
    assert result["decision_eligibility_asserted"] is False


def test_closes_economic_validity_audit_trail() -> None:
    result = close_authority_evidence_completeness_report_audit_trail(_final_audited("economic_validity"))
    assert result["closure_completed"] is True
    closed = result["closed"]
    assert isinstance(closed, dict)
    assert closed["complete"] is True
    assert closed["audit_trail"]["report"]["evidence_kind"] == "economic_validity"
    assert result["decision_eligibility_asserted"] is False


def test_closes_incomplete_audit_trail() -> None:
    final_audited = _final_audited("identity_time")
    envelope = final_audited["final_audited"]
    assert isinstance(envelope, dict)
    audit_trail = envelope["audit_trail"]
    assert isinstance(audit_trail, dict)
    report = audit_trail["report"]
    assert isinstance(report, dict)
    report["obligations"].remove("final_audit")
    report["missing_obligations"] = ["final_audit"]
    report["final_audit_integrated"] = False
    audit_trail["complete"] = False
    audit_trail["missing_obligations"] = ["final_audit"]
    audit_trail["final_audit_integrated"] = False
    envelope["complete"] = False
    envelope["missing_obligations"] = ["final_audit"]
    envelope["final_audit_integrated"] = False
    final_audited["final_audit_fingerprint"] = hashlib.sha256(_canonical_bytes(envelope)).hexdigest()
    result = close_authority_evidence_completeness_report_audit_trail(final_audited)
    assert result["closure_completed"] is True
    closed = result["closed"]
    assert isinstance(closed, dict)
    assert closed["complete"] is False
    assert closed["missing_obligations"] == ["final_audit"]
    assert closed["final_audit_integrated"] is False
    assert result["decision_eligibility_asserted"] is False


def test_rejects_fingerprint_mismatch() -> None:
    final_audited = _final_audited("identity_time")
    final_audited["final_audited"]["complete"] = False
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_FINAL_AUDIT_FINGERPRINT_MISMATCH"):
        close_authority_evidence_completeness_report_audit_trail(final_audited)


def test_rejects_point_in_time_decision() -> None:
    final_audited = _final_audited("identity_time")
    final_audited["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        close_authority_evidence_completeness_report_audit_trail(final_audited)


def test_rejects_healing() -> None:
    final_audited = _final_audited("identity_time")
    final_audited["final_audited"]["audit_trail"]["healed"] = True
    final_audited["final_audit_fingerprint"] = hashlib.sha256(
        _canonical_bytes(final_audited["final_audited"])
    ).hexdigest()
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"):
        close_authority_evidence_completeness_report_audit_trail(final_audited)
