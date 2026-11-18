"""Tests for native authority evidence completeness report audit-trail governance and replay integration."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from nse_quant.data_platform.native_authority_evidence_completeness_report_audit_trail_governance import (
    govern_authority_evidence_completeness_report_audit_trail_lifecycle,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-audit-trail-governance@1"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _lifecycle(kind: str) -> dict[str, Any]:
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
        "lifecycle": envelope,
        "lifecycle_fingerprint": hashlib.sha256(_canonical_bytes(envelope)).hexdigest(),
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def test_governs_identity_time_audit_trail_lifecycle() -> None:
    result = govern_authority_evidence_completeness_report_audit_trail_lifecycle(_lifecycle("identity_time"))
    assert result["governance_completed"] is True
    governed = result["governed"]
    assert isinstance(governed, dict)
    assert governed["complete"] is True
    assert governed["audit_trail"]["report"]["evidence_kind"] == "identity_time"
    assert governed["audit_integrated"] is True
    assert governed["orphan_check_integrated"] is True
    assert governed["final_audit_integrated"] is True
    assert result["decision_eligibility_asserted"] is False


def test_governs_availability_audit_trail_lifecycle() -> None:
    result = govern_authority_evidence_completeness_report_audit_trail_lifecycle(_lifecycle("availability"))
    assert result["governance_completed"] is True
    governed = result["governed"]
    assert isinstance(governed, dict)
    assert governed["complete"] is True
    assert governed["audit_trail"]["report"]["evidence_kind"] == "availability"
    assert result["decision_eligibility_asserted"] is False


def test_governs_economic_validity_audit_trail_lifecycle() -> None:
    result = govern_authority_evidence_completeness_report_audit_trail_lifecycle(_lifecycle("economic_validity"))
    assert result["governance_completed"] is True
    governed = result["governed"]
    assert isinstance(governed, dict)
    assert governed["complete"] is True
    assert governed["audit_trail"]["report"]["evidence_kind"] == "economic_validity"
    assert result["decision_eligibility_asserted"] is False


def test_governs_incomplete_audit_trail_lifecycle() -> None:
    lifecycle = _lifecycle("identity_time")
    envelope = lifecycle["lifecycle"]
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
    lifecycle["lifecycle_fingerprint"] = hashlib.sha256(_canonical_bytes(envelope)).hexdigest()
    result = govern_authority_evidence_completeness_report_audit_trail_lifecycle(lifecycle)
    assert result["governance_completed"] is True
    governed = result["governed"]
    assert isinstance(governed, dict)
    assert governed["complete"] is False
    assert governed["missing_obligations"] == ["final_audit"]
    assert governed["final_audit_integrated"] is False
    assert result["decision_eligibility_asserted"] is False


def test_rejects_fingerprint_mismatch() -> None:
    lifecycle = _lifecycle("identity_time")
    lifecycle["lifecycle"]["complete"] = False
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_LIFECYCLE_FINGERPRINT_MISMATCH"):
        govern_authority_evidence_completeness_report_audit_trail_lifecycle(lifecycle)


def test_rejects_point_in_time_decision() -> None:
    lifecycle = _lifecycle("identity_time")
    lifecycle["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        govern_authority_evidence_completeness_report_audit_trail_lifecycle(lifecycle)


def test_rejects_healing() -> None:
    lifecycle = _lifecycle("identity_time")
    lifecycle["lifecycle"]["audit_trail"]["healed"] = True
    lifecycle["lifecycle_fingerprint"] = hashlib.sha256(_canonical_bytes(lifecycle["lifecycle"])).hexdigest()
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"):
        govern_authority_evidence_completeness_report_audit_trail_lifecycle(lifecycle)
