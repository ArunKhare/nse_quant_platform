"""Tests for native authority evidence completeness report audit-trail persistence and replay."""

from __future__ import annotations

from typing import Any

import pytest

from nse_quant.data_platform.native_authority_evidence_completeness_report_audit_trail_persistence import (
    persist_authority_evidence_completeness_report_audit_trail,
    replay_authority_evidence_completeness_report_audit_trail,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-audit-trail-persistence@1"


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
    import hashlib
    import json

    def canonical_bytes(value: object) -> bytes:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    return {
        "version": VERSION,
        "reconciled": envelope,
        "reconciliation_fingerprint": hashlib.sha256(canonical_bytes(envelope)).hexdigest(),
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def test_persists_identity_time_audit_trail() -> None:
    result = persist_authority_evidence_completeness_report_audit_trail(_reconciled("identity_time"))
    assert result["persisted"] is True
    assert result["audit_trail"]["complete"] is True
    assert result["audit_trail"]["report"]["evidence_kind"] == "identity_time"
    assert result["audit_trail"]["audit_integrated"] is True
    assert result["audit_trail"]["orphan_check_integrated"] is True
    assert result["audit_trail"]["final_audit_integrated"] is True
    assert result["decision_eligibility_asserted"] is False


def test_persists_availability_audit_trail() -> None:
    result = persist_authority_evidence_completeness_report_audit_trail(_reconciled("availability"))
    assert result["persisted"] is True
    assert result["audit_trail"]["complete"] is True
    assert result["audit_trail"]["report"]["evidence_kind"] == "availability"
    assert result["decision_eligibility_asserted"] is False


def test_persists_economic_validity_audit_trail() -> None:
    result = persist_authority_evidence_completeness_report_audit_trail(_reconciled("economic_validity"))
    assert result["persisted"] is True
    assert result["audit_trail"]["complete"] is True
    assert result["audit_trail"]["report"]["evidence_kind"] == "economic_validity"
    assert result["decision_eligibility_asserted"] is False


def test_replays_persisted_audit_trail_exactly() -> None:
    persisted = persist_authority_evidence_completeness_report_audit_trail(_reconciled("identity_time"))
    result = replay_authority_evidence_completeness_report_audit_trail(persisted)
    assert result["replayed"] is True
    assert result["audit_trail"] == persisted["audit_trail"]
    assert result["audit_trail_fingerprint"] == persisted["audit_trail_fingerprint"]
    assert result["decision_eligibility_asserted"] is False


def test_rejects_audit_trail_fingerprint_mismatch() -> None:
    persisted = persist_authority_evidence_completeness_report_audit_trail(_reconciled("identity_time"))
    persisted["audit_trail"]["complete"] = False
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_AUDIT_TRAIL_FINGERPRINT_MISMATCH"):
        replay_authority_evidence_completeness_report_audit_trail(persisted)


def test_rejects_point_in_time_decision() -> None:
    reconciled = _reconciled("identity_time")
    reconciled["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        persist_authority_evidence_completeness_report_audit_trail(reconciled)


def test_rejects_healing() -> None:
    reconciled = _reconciled("identity_time")
    reconciled["reconciled"]["report"]["healed"] = True
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"):
        persist_authority_evidence_completeness_report_audit_trail(reconciled)
