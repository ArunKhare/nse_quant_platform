import hashlib
import json

import pytest

from nse_quant.data_platform.native_authority_evidence_completeness_report_audit_trail_persistence_replay import (
    LIFECYCLE_STAGES,
    VERSION,
    persist_authority_evidence_completeness_report_audit_trail,
    replay_authority_evidence_completeness_report_audit_trail,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _enforced(obligations=None):
    audit_trail = {
        "healed": False,
        "report": {
            "obligations": obligations
            if obligations is not None
            else ["original_first_write", "audit", "orphan_check", "final_audit"]
        },
    }
    envelope = {
        "version": "native-authority-evidence-completeness-report-audit-trail-enforcement@1",
        "audit_trail": audit_trail,
        "complete": obligations is None,
        "missing_obligations": []
        if obligations is None
        else [
            item for item in ["original_first_write", "audit", "orphan_check", "final_audit"] if item not in obligations
        ],
        "audit_integrated": "audit" in (obligations or []),
        "orphan_check_integrated": "orphan_check" in (obligations or []),
        "final_audit_integrated": "final_audit" in (obligations or []),
        "lifecycle_stages": list(LIFECYCLE_STAGES),
        "healed": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "enforcement_completed": True,
        "version": VERSION,
        "enforced": envelope,
        "enforcement_fingerprint": hashlib.sha256(_canonical(envelope)).hexdigest(),
        "decision_eligibility_asserted": False,
    }


def test_persists_and_replays_complete_enforced_audit_trail():
    persisted = persist_authority_evidence_completeness_report_audit_trail(_enforced())
    assert persisted["persistence_completed"] is True
    assert persisted["version"] == VERSION
    assert persisted["decision_eligibility_asserted"] is False
    envelope = persisted["persisted"]
    assert envelope["complete"] is True
    assert envelope["missing_obligations"] == []
    assert envelope["lifecycle_stages"] == list(LIFECYCLE_STAGES)
    assert envelope["healed"] is False
    assert persisted["persistence_fingerprint"] == hashlib.sha256(_canonical(envelope)).hexdigest()
    replayed = replay_authority_evidence_completeness_report_audit_trail(persisted)
    assert replayed["replayed"] is True
    assert replayed["complete"] is True
    assert replayed["missing_obligations"] == []
    assert replayed["enforced_envelope"] == _enforced()["enforced"]
    assert replayed["enforcement_fingerprint"] == _enforced()["enforcement_fingerprint"]
    assert replayed["decision_eligibility_asserted"] is False


def test_preserves_incomplete_obligations_without_healing():
    persisted = persist_authority_evidence_completeness_report_audit_trail(_enforced(["original_first_write", "audit"]))
    assert persisted["persistence_completed"] is True
    envelope = persisted["persisted"]
    assert envelope["complete"] is False
    assert envelope["missing_obligations"] == ["orphan_check", "final_audit"]
    assert envelope["audit_integrated"] is True
    assert envelope["orphan_check_integrated"] is False
    assert envelope["final_audit_integrated"] is False
    replayed = replay_authority_evidence_completeness_report_audit_trail(persisted)
    assert replayed["complete"] is False
    assert replayed["missing_obligations"] == ["orphan_check", "final_audit"]
    assert replayed["orphan_check_integrated"] is False
    assert replayed["final_audit_integrated"] is False
    assert replayed["healed"] is False
    assert replayed["decision_eligibility_asserted"] is False


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda value: value.update({"point_in_time_decision": True}), "POINT_IN_TIME_DECISION"),
        (
            lambda value: value.update({"decision_eligibility_asserted": True}),
            "AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN",
        ),
        (lambda value: value.update({"enforcement_completed": False}), "AUTHORITY_EVIDENCE_ENFORCEMENT_INCOMPLETE"),
        (
            lambda value: value.update({"enforcement_fingerprint": "short"}),
            "AUTHORITY_EVIDENCE_ENFORCEMENT_FINGERPRINT_INVALID",
        ),
        (
            lambda value: value.update({"enforcement_fingerprint": "0" * 64}),
            "AUTHORITY_EVIDENCE_ENFORCEMENT_FINGERPRINT_MISMATCH",
        ),
        (lambda value: value["enforced"].update({"healed": True}), "AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"),
    ],
)
def test_rejects_forbidden_persistence_inputs(mutation, error):
    value = _enforced()
    mutation(value)
    with pytest.raises(Rejected) as exc:
        persist_authority_evidence_completeness_report_audit_trail(value)
    assert exc.value.args[0] == error


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda value: value.update({"point_in_time_decision": True}), "POINT_IN_TIME_DECISION"),
        (
            lambda value: value.update({"decision_eligibility_asserted": True}),
            "AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN",
        ),
        (lambda value: value.update({"persistence_completed": False}), "AUTHORITY_EVIDENCE_PERSISTENCE_INCOMPLETE"),
        (
            lambda value: value.update({"persistence_fingerprint": "short"}),
            "AUTHORITY_EVIDENCE_PERSISTENCE_FINGERPRINT_INVALID",
        ),
        (
            lambda value: value.update({"persistence_fingerprint": "0" * 64}),
            "AUTHORITY_EVIDENCE_PERSISTENCE_FINGERPRINT_MISMATCH",
        ),
        (lambda value: value["persisted"].update({"healed": True}), "AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"),
    ],
)
def test_rejects_forbidden_replay_inputs(mutation, error):
    value = persist_authority_evidence_completeness_report_audit_trail(_enforced())
    mutation(value)
    with pytest.raises(Rejected) as exc:
        replay_authority_evidence_completeness_report_audit_trail(value)
    assert exc.value.args[0] == error
