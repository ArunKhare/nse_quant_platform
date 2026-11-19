"""Tests for native authority evidence completeness report audit-trail lifecycle and replay integration."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from nse_quant.data_platform.native_authority_evidence_completeness_report_audit_trail_lifecycle import (
    manage_authority_evidence_completeness_report_audit_trail_lifecycle,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-audit-trail-lifecycle@1"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _retained(kind: str) -> dict[str, Any]:
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
        "retained": envelope,
        "retention_fingerprint": hashlib.sha256(_canonical_bytes(envelope)).hexdigest(),
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def test_manages_identity_time_audit_trail_lifecycle() -> None:
    result = manage_authority_evidence_completeness_report_audit_trail_lifecycle(_retained("identity_time"))
    assert result["lifecycle_completed"] is True
    lifecycle = result["lifecycle"]
    assert isinstance(lifecycle, dict)
    assert lifecycle["complete"] is True
    assert lifecycle["audit_trail"]["report"]["evidence_kind"] == "identity_time"
    assert lifecycle["audit_integrated"] is True
    assert lifecycle["orphan_check_integrated"] is True
    assert lifecycle["final_audit_integrated"] is True
    assert result["decision_eligibility_asserted"] is False


def test_manages_availability_audit_trail_lifecycle() -> None:
    result = manage_authority_evidence_completeness_report_audit_trail_lifecycle(_retained("availability"))
    assert result["lifecycle_completed"] is True
    lifecycle = result["lifecycle"]
    assert isinstance(lifecycle, dict)
    assert lifecycle["complete"] is True
    assert lifecycle["audit_trail"]["report"]["evidence_kind"] == "availability"
    assert result["decision_eligibility_asserted"] is False


def test_manages_economic_validity_audit_trail_lifecycle() -> None:
    result = manage_authority_evidence_completeness_report_audit_trail_lifecycle(_retained("economic_validity"))
    assert result["lifecycle_completed"] is True
    lifecycle = result["lifecycle"]
    assert isinstance(lifecycle, dict)
    assert lifecycle["complete"] is True
    assert lifecycle["audit_trail"]["report"]["evidence_kind"] == "economic_validity"
    assert result["decision_eligibility_asserted"] is False


def test_manages_incomplete_audit_trail_lifecycle() -> None:
    retained = _retained("identity_time")
    envelope = retained["retained"]
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
    retained["retention_fingerprint"] = hashlib.sha256(_canonical_bytes(envelope)).hexdigest()
    result = manage_authority_evidence_completeness_report_audit_trail_lifecycle(retained)
    assert result["lifecycle_completed"] is True
    lifecycle = result["lifecycle"]
    assert isinstance(lifecycle, dict)
    assert lifecycle["complete"] is False
    assert lifecycle["missing_obligations"] == ["final_audit"]
    assert lifecycle["final_audit_integrated"] is False
    assert result["decision_eligibility_asserted"] is False


def test_rejects_fingerprint_mismatch() -> None:
    retained = _retained("identity_time")
    retained["retained"]["complete"] = False
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_RETENTION_FINGERPRINT_MISMATCH"):
        manage_authority_evidence_completeness_report_audit_trail_lifecycle(retained)


def test_rejects_point_in_time_decision() -> None:
    retained = _retained("identity_time")
    retained["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        manage_authority_evidence_completeness_report_audit_trail_lifecycle(retained)


def test_rejects_healing() -> None:
    retained = _retained("identity_time")
    retained["retained"]["audit_trail"]["healed"] = True
    retained["retention_fingerprint"] = hashlib.sha256(_canonical_bytes(retained["retained"])).hexdigest()
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"):
        manage_authority_evidence_completeness_report_audit_trail_lifecycle(retained)
