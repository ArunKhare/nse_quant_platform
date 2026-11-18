"""Tests for native authority evidence completeness report audit-trail retention and replay integration."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from nse_quant.data_platform.native_authority_evidence_completeness_report_audit_trail_retention import (
    retain_authority_evidence_completeness_report_audit_trail,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-audit-trail-retention@1"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _archived(kind: str) -> dict[str, Any]:
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
        "archived": envelope,
        "archival_fingerprint": hashlib.sha256(_canonical_bytes(envelope)).hexdigest(),
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def test_retains_identity_time_audit_trail() -> None:
    result = retain_authority_evidence_completeness_report_audit_trail(_archived("identity_time"))
    assert result["retention_completed"] is True
    retained = result["retained"]
    assert isinstance(retained, dict)
    assert retained["complete"] is True
    assert retained["audit_trail"]["report"]["evidence_kind"] == "identity_time"
    assert retained["audit_integrated"] is True
    assert retained["orphan_check_integrated"] is True
    assert retained["final_audit_integrated"] is True
    assert result["decision_eligibility_asserted"] is False


def test_retains_availability_audit_trail() -> None:
    result = retain_authority_evidence_completeness_report_audit_trail(_archived("availability"))
    assert result["retention_completed"] is True
    retained = result["retained"]
    assert isinstance(retained, dict)
    assert retained["complete"] is True
    assert retained["audit_trail"]["report"]["evidence_kind"] == "availability"
    assert result["decision_eligibility_asserted"] is False


def test_retains_economic_validity_audit_trail() -> None:
    result = retain_authority_evidence_completeness_report_audit_trail(_archived("economic_validity"))
    assert result["retention_completed"] is True
    retained = result["retained"]
    assert isinstance(retained, dict)
    assert retained["complete"] is True
    assert retained["audit_trail"]["report"]["evidence_kind"] == "economic_validity"
    assert result["decision_eligibility_asserted"] is False


def test_retains_incomplete_audit_trail() -> None:
    archived = _archived("identity_time")
    envelope = archived["archived"]
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
    archived["archival_fingerprint"] = hashlib.sha256(_canonical_bytes(envelope)).hexdigest()
    result = retain_authority_evidence_completeness_report_audit_trail(archived)
    assert result["retention_completed"] is True
    retained = result["retained"]
    assert isinstance(retained, dict)
    assert retained["complete"] is False
    assert retained["missing_obligations"] == ["final_audit"]
    assert retained["final_audit_integrated"] is False
    assert result["decision_eligibility_asserted"] is False


def test_rejects_fingerprint_mismatch() -> None:
    archived = _archived("identity_time")
    archived["archived"]["complete"] = False
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_ARCHIVAL_FINGERPRINT_MISMATCH"):
        retain_authority_evidence_completeness_report_audit_trail(archived)


def test_rejects_point_in_time_decision() -> None:
    archived = _archived("identity_time")
    archived["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        retain_authority_evidence_completeness_report_audit_trail(archived)


def test_rejects_healing() -> None:
    archived = _archived("identity_time")
    archived["archived"]["audit_trail"]["healed"] = True
    archived["archival_fingerprint"] = hashlib.sha256(_canonical_bytes(archived["archived"])).hexdigest()
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"):
        retain_authority_evidence_completeness_report_audit_trail(archived)
