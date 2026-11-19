"""Tests for native authority evidence completeness report audit-trail final audit and replay integration."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from nse_quant.data_platform.native_authority_evidence_completeness_report_audit_trail_final_audit import (
    final_audit_authority_evidence_completeness_report_audit_trail,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-audit-trail-final-audit@1"


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
        "reconciled": envelope,
        "reconciliation_fingerprint": hashlib.sha256(_canonical_bytes(envelope)).hexdigest(),
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def test_final_audits_identity_time_audit_trail() -> None:
    result = final_audit_authority_evidence_completeness_report_audit_trail(_reconciled("identity_time"))
    assert result["final_audit_completed"] is True
    final_audited = result["final_audited"]
    assert isinstance(final_audited, dict)
    assert final_audited["complete"] is True
    assert final_audited["audit_trail"]["report"]["evidence_kind"] == "identity_time"
    assert final_audited["audit_integrated"] is True
    assert final_audited["orphan_check_integrated"] is True
    assert final_audited["final_audit_integrated"] is True
    assert result["decision_eligibility_asserted"] is False


def test_final_audits_availability_audit_trail() -> None:
    result = final_audit_authority_evidence_completeness_report_audit_trail(_reconciled("availability"))
    assert result["final_audit_completed"] is True
    final_audited = result["final_audited"]
    assert isinstance(final_audited, dict)
    assert final_audited["complete"] is True
    assert final_audited["audit_trail"]["report"]["evidence_kind"] == "availability"
    assert result["decision_eligibility_asserted"] is False


def test_final_audits_economic_validity_audit_trail() -> None:
    result = final_audit_authority_evidence_completeness_report_audit_trail(_reconciled("economic_validity"))
    assert result["final_audit_completed"] is True
    final_audited = result["final_audited"]
    assert isinstance(final_audited, dict)
    assert final_audited["complete"] is True
    assert final_audited["audit_trail"]["report"]["evidence_kind"] == "economic_validity"
    assert result["decision_eligibility_asserted"] is False


def test_final_audits_incomplete_audit_trail() -> None:
    reconciled = _reconciled("identity_time")
    envelope = reconciled["reconciled"]
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
    reconciled["reconciliation_fingerprint"] = hashlib.sha256(_canonical_bytes(envelope)).hexdigest()
    result = final_audit_authority_evidence_completeness_report_audit_trail(reconciled)
    assert result["final_audit_completed"] is True
    final_audited = result["final_audited"]
    assert isinstance(final_audited, dict)
    assert final_audited["complete"] is False
    assert final_audited["missing_obligations"] == ["final_audit"]
    assert final_audited["final_audit_integrated"] is False
    assert result["decision_eligibility_asserted"] is False


def test_rejects_fingerprint_mismatch() -> None:
    reconciled = _reconciled("identity_time")
    reconciled["reconciled"]["complete"] = False
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_RECONCILIATION_FINGERPRINT_MISMATCH"):
        final_audit_authority_evidence_completeness_report_audit_trail(reconciled)


def test_rejects_point_in_time_decision() -> None:
    reconciled = _reconciled("identity_time")
    reconciled["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        final_audit_authority_evidence_completeness_report_audit_trail(reconciled)


def test_rejects_healing() -> None:
    reconciled = _reconciled("identity_time")
    reconciled["reconciled"]["audit_trail"]["healed"] = True
    reconciled["reconciliation_fingerprint"] = hashlib.sha256(_canonical_bytes(reconciled["reconciled"])).hexdigest()
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"):
        final_audit_authority_evidence_completeness_report_audit_trail(reconciled)
