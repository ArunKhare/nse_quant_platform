"""Tests for native authority evidence completeness report audit-trail policy and replay integration."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from nse_quant.data_platform.native_authority_evidence_completeness_report_audit_trail_policy import (
    apply_policy_authority_evidence_completeness_report_audit_trail_lifecycle,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-audit-trail-policy@1"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _governed(kind: str) -> dict[str, Any]:
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
        "governed": envelope,
        "governance_fingerprint": hashlib.sha256(_canonical_bytes(envelope)).hexdigest(),
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def test_applies_policy_identity_time_audit_trail_lifecycle() -> None:
    result = apply_policy_authority_evidence_completeness_report_audit_trail_lifecycle(_governed("identity_time"))
    assert result["policy_applied_completed"] is True
    policy_applied = result["policy_applied"]
    assert isinstance(policy_applied, dict)
    assert policy_applied["complete"] is True
    assert policy_applied["audit_trail"]["report"]["evidence_kind"] == "identity_time"
    assert policy_applied["audit_integrated"] is True
    assert policy_applied["orphan_check_integrated"] is True
    assert policy_applied["final_audit_integrated"] is True
    assert result["decision_eligibility_asserted"] is False


def test_applies_policy_availability_audit_trail_lifecycle() -> None:
    result = apply_policy_authority_evidence_completeness_report_audit_trail_lifecycle(_governed("availability"))
    assert result["policy_applied_completed"] is True
    policy_applied = result["policy_applied"]
    assert isinstance(policy_applied, dict)
    assert policy_applied["complete"] is True
    assert policy_applied["audit_trail"]["report"]["evidence_kind"] == "availability"
    assert result["decision_eligibility_asserted"] is False


def test_applies_policy_economic_validity_audit_trail_lifecycle() -> None:
    result = apply_policy_authority_evidence_completeness_report_audit_trail_lifecycle(_governed("economic_validity"))
    assert result["policy_applied_completed"] is True
    policy_applied = result["policy_applied"]
    assert isinstance(policy_applied, dict)
    assert policy_applied["complete"] is True
    assert policy_applied["audit_trail"]["report"]["evidence_kind"] == "economic_validity"
    assert result["decision_eligibility_asserted"] is False


def test_applies_policy_incomplete_audit_trail_lifecycle() -> None:
    governed = _governed("identity_time")
    envelope = governed["governed"]
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
    governed["governance_fingerprint"] = hashlib.sha256(_canonical_bytes(envelope)).hexdigest()
    result = apply_policy_authority_evidence_completeness_report_audit_trail_lifecycle(governed)
    assert result["policy_applied_completed"] is True
    policy_applied = result["policy_applied"]
    assert isinstance(policy_applied, dict)
    assert policy_applied["complete"] is False
    assert policy_applied["missing_obligations"] == ["final_audit"]
    assert policy_applied["final_audit_integrated"] is False
    assert result["decision_eligibility_asserted"] is False


def test_rejects_fingerprint_mismatch() -> None:
    governed = _governed("identity_time")
    governed["governed"]["complete"] = False
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_GOVERNANCE_FINGERPRINT_MISMATCH"):
        apply_policy_authority_evidence_completeness_report_audit_trail_lifecycle(governed)


def test_rejects_point_in_time_decision() -> None:
    governed = _governed("identity_time")
    governed["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        apply_policy_authority_evidence_completeness_report_audit_trail_lifecycle(governed)


def test_rejects_healing() -> None:
    governed = _governed("identity_time")
    governed["governed"]["audit_trail"]["healed"] = True
    governed["governance_fingerprint"] = hashlib.sha256(_canonical_bytes(governed["governed"])).hexdigest()
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"):
        apply_policy_authority_evidence_completeness_report_audit_trail_lifecycle(governed)
