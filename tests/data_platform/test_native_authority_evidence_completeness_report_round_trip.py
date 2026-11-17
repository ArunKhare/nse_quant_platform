"""Tests for native authority evidence completeness report round-trip and audit integration."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from nse_quant.data_platform.native_authority_evidence_completeness_report_round_trip import (
    round_trip_authority_evidence_completeness_report,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-round-trip@1"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _exported(kind: str) -> dict[str, Any]:
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
    export = {
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
        "export": export,
        "export_fingerprint": hashlib.sha256(_canonical_bytes(export)).hexdigest(),
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def test_round_trips_identity_time_completeness_report() -> None:
    result = round_trip_authority_evidence_completeness_report(_exported("identity_time"))
    round_tripped = result["round_tripped"]
    assert isinstance(round_tripped, dict)
    assert round_tripped["complete"] is True
    assert round_tripped["report"]["evidence_kind"] == "identity_time"
    assert round_tripped["audit_integrated"] is True
    assert round_tripped["orphan_check_integrated"] is True
    assert round_tripped["final_audit_integrated"] is True
    assert result["decision_eligibility_asserted"] is False


def test_round_trips_availability_completeness_report() -> None:
    result = round_trip_authority_evidence_completeness_report(_exported("availability"))
    round_tripped = result["round_tripped"]
    assert isinstance(round_tripped, dict)
    assert round_tripped["complete"] is True
    assert round_tripped["report"]["evidence_kind"] == "availability"
    assert result["decision_eligibility_asserted"] is False


def test_round_trips_economic_validity_completeness_report() -> None:
    result = round_trip_authority_evidence_completeness_report(_exported("economic_validity"))
    round_tripped = result["round_tripped"]
    assert isinstance(round_tripped, dict)
    assert round_tripped["complete"] is True
    assert round_tripped["report"]["evidence_kind"] == "economic_validity"
    assert result["decision_eligibility_asserted"] is False


def test_round_trips_incomplete_report() -> None:
    exported = _exported("identity_time")
    export = exported["export"]
    assert isinstance(export, dict)
    report = export["report"]
    assert isinstance(report, dict)
    report["obligations"].remove("final_audit")
    report["missing_obligations"] = ["final_audit"]
    report["final_audit_integrated"] = False
    export["complete"] = False
    export["missing_obligations"] = ["final_audit"]
    export["final_audit_integrated"] = False
    exported["export_fingerprint"] = hashlib.sha256(_canonical_bytes(export)).hexdigest()
    result = round_trip_authority_evidence_completeness_report(exported)
    round_tripped = result["round_tripped"]
    assert isinstance(round_tripped, dict)
    assert round_tripped["complete"] is False
    assert round_tripped["missing_obligations"] == ["final_audit"]
    assert round_tripped["final_audit_integrated"] is False
    assert result["decision_eligibility_asserted"] is False


def test_rejects_fingerprint_mismatch() -> None:
    exported = _exported("identity_time")
    exported["export"]["complete"] = False
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_EXPORT_FINGERPRINT_MISMATCH"):
        round_trip_authority_evidence_completeness_report(exported)


def test_rejects_point_in_time_decision() -> None:
    exported = _exported("identity_time")
    exported["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        round_trip_authority_evidence_completeness_report(exported)


def test_rejects_healing() -> None:
    exported = _exported("identity_time")
    exported["export"]["report"]["healed"] = True
    exported["export_fingerprint"] = hashlib.sha256(_canonical_bytes(exported["export"])).hexdigest()
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"):
        round_trip_authority_evidence_completeness_report(exported)
