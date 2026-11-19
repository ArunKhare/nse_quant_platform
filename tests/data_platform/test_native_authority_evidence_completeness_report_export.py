"""Tests for native authority evidence completeness report export and audit integration."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from nse_quant.data_platform.native_authority_evidence_completeness_report_export import (
    export_authority_evidence_completeness_report,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-export@1"


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
    return {
        "version": VERSION,
        "report": report,
        "report_fingerprint": hashlib.sha256(_canonical_bytes(report)).hexdigest(),
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def test_exports_identity_time_completeness_report() -> None:
    result = export_authority_evidence_completeness_report(_persisted("identity_time"))
    assert result["exported"] is True
    assert result["export"]["complete"] is True
    assert result["export"]["report"]["evidence_kind"] == "identity_time"
    assert result["export"]["audit_integrated"] is True
    assert result["export"]["orphan_check_integrated"] is True
    assert result["export"]["final_audit_integrated"] is True
    assert result["decision_eligibility_asserted"] is False


def test_exports_availability_completeness_report() -> None:
    result = export_authority_evidence_completeness_report(_persisted("availability"))
    assert result["exported"] is True
    assert result["export"]["complete"] is True
    assert result["export"]["report"]["evidence_kind"] == "availability"
    assert result["decision_eligibility_asserted"] is False


def test_exports_economic_validity_completeness_report() -> None:
    result = export_authority_evidence_completeness_report(_persisted("economic_validity"))
    assert result["exported"] is True
    assert result["export"]["complete"] is True
    assert result["export"]["report"]["evidence_kind"] == "economic_validity"
    assert result["decision_eligibility_asserted"] is False


def test_exports_incomplete_report() -> None:
    persisted = _persisted("identity_time")
    report = persisted["report"]
    assert isinstance(report, dict)
    report["obligations"].remove("final_audit")
    report["missing_obligations"] = ["final_audit"]
    report["final_audit_integrated"] = False
    persisted["report_fingerprint"] = hashlib.sha256(_canonical_bytes(report)).hexdigest()
    result = export_authority_evidence_completeness_report(persisted)
    assert result["exported"] is True
    assert result["export"]["complete"] is False
    assert result["export"]["missing_obligations"] == ["final_audit"]
    assert result["export"]["final_audit_integrated"] is False
    assert result["decision_eligibility_asserted"] is False


def test_rejects_fingerprint_mismatch() -> None:
    persisted = _persisted("identity_time")
    persisted["report"]["complete"] = False
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_REPORT_FINGERPRINT_MISMATCH"):
        export_authority_evidence_completeness_report(persisted)


def test_rejects_point_in_time_decision() -> None:
    persisted = _persisted("identity_time")
    persisted["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        export_authority_evidence_completeness_report(persisted)


def test_rejects_healing() -> None:
    persisted = _persisted("identity_time")
    persisted["report"]["healed"] = True
    persisted["report_fingerprint"] = hashlib.sha256(_canonical_bytes(persisted["report"])).hexdigest()
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"):
        export_authority_evidence_completeness_report(persisted)
