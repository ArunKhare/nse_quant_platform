"""Tests for native authority evidence completeness report reconciliation and audit integration."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from nse_quant.data_platform.native_authority_evidence_completeness_report_reconciliation import (
    reconcile_authority_evidence_completeness_report,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-reconciliation@1"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _accepted(kind: str) -> dict[str, Any]:
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
        "accepted": envelope,
        "acceptance_fingerprint": hashlib.sha256(_canonical_bytes(envelope)).hexdigest(),
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def test_reconciles_identity_time_completeness_report() -> None:
    result = reconcile_authority_evidence_completeness_report(_accepted("identity_time"))
    reconciled = result["reconciled"]
    assert isinstance(reconciled, dict)
    assert reconciled["complete"] is True
    assert reconciled["report"]["evidence_kind"] == "identity_time"
    assert reconciled["audit_integrated"] is True
    assert reconciled["orphan_check_integrated"] is True
    assert reconciled["final_audit_integrated"] is True
    assert result["decision_eligibility_asserted"] is False


def test_reconciles_availability_completeness_report() -> None:
    result = reconcile_authority_evidence_completeness_report(_accepted("availability"))
    reconciled = result["reconciled"]
    assert isinstance(reconciled, dict)
    assert reconciled["complete"] is True
    assert reconciled["report"]["evidence_kind"] == "availability"
    assert result["decision_eligibility_asserted"] is False


def test_reconciles_economic_validity_completeness_report() -> None:
    result = reconcile_authority_evidence_completeness_report(_accepted("economic_validity"))
    reconciled = result["reconciled"]
    assert isinstance(reconciled, dict)
    assert reconciled["complete"] is True
    assert reconciled["report"]["evidence_kind"] == "economic_validity"
    assert result["decision_eligibility_asserted"] is False


def test_reconciles_incomplete_report() -> None:
    accepted = _accepted("identity_time")
    envelope = accepted["accepted"]
    assert isinstance(envelope, dict)
    report = envelope["report"]
    assert isinstance(report, dict)
    report["obligations"].remove("final_audit")
    report["missing_obligations"] = ["final_audit"]
    report["final_audit_integrated"] = False
    envelope["complete"] = False
    envelope["missing_obligations"] = ["final_audit"]
    envelope["final_audit_integrated"] = False
    accepted["acceptance_fingerprint"] = hashlib.sha256(_canonical_bytes(envelope)).hexdigest()
    result = reconcile_authority_evidence_completeness_report(accepted)
    reconciled = result["reconciled"]
    assert isinstance(reconciled, dict)
    assert reconciled["complete"] is False
    assert reconciled["missing_obligations"] == ["final_audit"]
    assert reconciled["final_audit_integrated"] is False
    assert result["decision_eligibility_asserted"] is False


def test_rejects_fingerprint_mismatch() -> None:
    accepted = _accepted("identity_time")
    accepted["accepted"]["complete"] = False
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_ACCEPTANCE_FINGERPRINT_MISMATCH"):
        reconcile_authority_evidence_completeness_report(accepted)


def test_rejects_point_in_time_decision() -> None:
    accepted = _accepted("identity_time")
    accepted["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        reconcile_authority_evidence_completeness_report(accepted)


def test_rejects_healing() -> None:
    accepted = _accepted("identity_time")
    accepted["accepted"]["report"]["healed"] = True
    accepted["acceptance_fingerprint"] = hashlib.sha256(_canonical_bytes(accepted["accepted"])).hexdigest()
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"):
        reconcile_authority_evidence_completeness_report(accepted)
