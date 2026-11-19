"""Tests for native authority evidence completeness report audit-trail query and replay integration."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from nse_quant.data_platform.native_authority_evidence_completeness_report_audit_trail_query import (
    query_authority_evidence_completeness_report_audit_trail,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-audit-trail-query@1"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _persisted(kind: str) -> dict[str, Any]:
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
        "audit_trail_fingerprint": hashlib.sha256(_canonical_bytes(audit_trail)).hexdigest(),
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def test_queries_identity_time_audit_trail() -> None:
    result = query_authority_evidence_completeness_report_audit_trail(_persisted("identity_time"))
    assert result["queried"] is True
    assert result["complete"] is True
    assert result["audit_trail"]["report"]["evidence_kind"] == "identity_time"
    assert result["audit_integrated"] is True
    assert result["orphan_check_integrated"] is True
    assert result["final_audit_integrated"] is True
    assert result["decision_eligibility_asserted"] is False


def test_queries_availability_audit_trail() -> None:
    result = query_authority_evidence_completeness_report_audit_trail(_persisted("availability"))
    assert result["queried"] is True
    assert result["complete"] is True
    assert result["audit_trail"]["report"]["evidence_kind"] == "availability"
    assert result["decision_eligibility_asserted"] is False


def test_queries_economic_validity_audit_trail() -> None:
    result = query_authority_evidence_completeness_report_audit_trail(_persisted("economic_validity"))
    assert result["queried"] is True
    assert result["complete"] is True
    assert result["audit_trail"]["report"]["evidence_kind"] == "economic_validity"
    assert result["decision_eligibility_asserted"] is False


def test_queries_incomplete_audit_trail() -> None:
    persisted = _persisted("identity_time")
    audit_trail = persisted["audit_trail"]
    assert isinstance(audit_trail, dict)
    report = audit_trail["report"]
    assert isinstance(report, dict)
    report["obligations"].remove("final_audit")
    report["missing_obligations"] = ["final_audit"]
    report["final_audit_integrated"] = False
    audit_trail["complete"] = False
    audit_trail["missing_obligations"] = ["final_audit"]
    audit_trail["final_audit_integrated"] = False
    persisted["audit_trail_fingerprint"] = hashlib.sha256(_canonical_bytes(audit_trail)).hexdigest()
    result = query_authority_evidence_completeness_report_audit_trail(persisted)
    assert result["queried"] is True
    assert result["complete"] is False
    assert result["missing_obligations"] == ["final_audit"]
    assert result["final_audit_integrated"] is False
    assert result["decision_eligibility_asserted"] is False


def test_rejects_fingerprint_mismatch() -> None:
    persisted = _persisted("identity_time")
    persisted["audit_trail"]["complete"] = False
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_AUDIT_TRAIL_FINGERPRINT_MISMATCH"):
        query_authority_evidence_completeness_report_audit_trail(persisted)


def test_rejects_point_in_time_decision() -> None:
    persisted = _persisted("identity_time")
    persisted["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        query_authority_evidence_completeness_report_audit_trail(persisted)


def test_rejects_healing() -> None:
    persisted = _persisted("identity_time")
    persisted["audit_trail"]["healed"] = True
    persisted["audit_trail_fingerprint"] = hashlib.sha256(_canonical_bytes(persisted["audit_trail"])).hexdigest()
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"):
        query_authority_evidence_completeness_report_audit_trail(persisted)
