"""Tests for native authority evidence completeness report audit-trail archival and replay integration."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from nse_quant.data_platform.native_authority_evidence_completeness_report_audit_trail_archival import (
    archive_authority_evidence_completeness_report_audit_trail,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-audit-trail-archival@1"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _closed(kind: str) -> dict[str, Any]:
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
        "closed": envelope,
        "closure_fingerprint": hashlib.sha256(_canonical_bytes(envelope)).hexdigest(),
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def test_archives_identity_time_audit_trail() -> None:
    result = archive_authority_evidence_completeness_report_audit_trail(_closed("identity_time"))
    assert result["archival_completed"] is True
    archived = result["archived"]
    assert isinstance(archived, dict)
    assert archived["complete"] is True
    assert archived["audit_trail"]["report"]["evidence_kind"] == "identity_time"
    assert archived["audit_integrated"] is True
    assert archived["orphan_check_integrated"] is True
    assert archived["final_audit_integrated"] is True
    assert result["decision_eligibility_asserted"] is False


def test_archives_availability_audit_trail() -> None:
    result = archive_authority_evidence_completeness_report_audit_trail(_closed("availability"))
    assert result["archival_completed"] is True
    archived = result["archived"]
    assert isinstance(archived, dict)
    assert archived["complete"] is True
    assert archived["audit_trail"]["report"]["evidence_kind"] == "availability"
    assert result["decision_eligibility_asserted"] is False


def test_archives_economic_validity_audit_trail() -> None:
    result = archive_authority_evidence_completeness_report_audit_trail(_closed("economic_validity"))
    assert result["archival_completed"] is True
    archived = result["archived"]
    assert isinstance(archived, dict)
    assert archived["complete"] is True
    assert archived["audit_trail"]["report"]["evidence_kind"] == "economic_validity"
    assert result["decision_eligibility_asserted"] is False


def test_archives_incomplete_audit_trail() -> None:
    closed = _closed("identity_time")
    envelope = closed["closed"]
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
    closed["closure_fingerprint"] = hashlib.sha256(_canonical_bytes(envelope)).hexdigest()
    result = archive_authority_evidence_completeness_report_audit_trail(closed)
    assert result["archival_completed"] is True
    archived = result["archived"]
    assert isinstance(archived, dict)
    assert archived["complete"] is False
    assert archived["missing_obligations"] == ["final_audit"]
    assert archived["final_audit_integrated"] is False
    assert result["decision_eligibility_asserted"] is False


def test_rejects_fingerprint_mismatch() -> None:
    closed = _closed("identity_time")
    closed["closed"]["complete"] = False
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_CLOSURE_FINGERPRINT_MISMATCH"):
        archive_authority_evidence_completeness_report_audit_trail(closed)


def test_rejects_point_in_time_decision() -> None:
    closed = _closed("identity_time")
    closed["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        archive_authority_evidence_completeness_report_audit_trail(closed)


def test_rejects_healing() -> None:
    closed = _closed("identity_time")
    closed["closed"]["audit_trail"]["healed"] = True
    closed["closure_fingerprint"] = hashlib.sha256(_canonical_bytes(closed["closed"])).hexdigest()
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"):
        archive_authority_evidence_completeness_report_audit_trail(closed)
