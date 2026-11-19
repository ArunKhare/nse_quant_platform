import hashlib
import json

import pytest

from nse_quant.data_platform import (
    native_authority_evidence_completeness_report_audit_trail_retention_expiry_governance as retention_report,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = retention_report.VERSION


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _persisted(persisted_at="2026-11-18T00:00:00+00:00"):
    audit_trail = {
        "healed": False,
        "report": {"obligations": ["original_first_write", "audit", "orphan_check", "final_audit"]},
    }
    enforced_envelope = {
        "version": "native-authority-evidence-completeness-report-audit-trail-enforcement@1",
        "audit_trail": audit_trail,
        "complete": True,
        "missing_obligations": [],
        "audit_integrated": True,
        "orphan_check_integrated": True,
        "final_audit_integrated": True,
        "lifecycle_stages": [
            "retained",
            "validated",
            "reconciled",
            "audited",
            "orphan_checked",
            "final_audited",
            "persisted",
        ],
        "healed": False,
        "decision_eligibility_asserted": False,
    }
    persisted_envelope = {
        "version": "native-authority-evidence-completeness-report-audit-trail-persistence-replay@1",
        "enforced_envelope": enforced_envelope,
        "enforcement_fingerprint": hashlib.sha256(_canonical(enforced_envelope)).hexdigest(),
        "complete": True,
        "missing_obligations": [],
        "audit_integrated": True,
        "orphan_check_integrated": True,
        "final_audit_integrated": True,
        "lifecycle_stages": [
            "retained",
            "validated",
            "reconciled",
            "audited",
            "orphan_checked",
            "final_audited",
            "persisted",
        ],
        "persisted_at": persisted_at,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "persistence_completed": True,
        "version": VERSION,
        "persisted": persisted_envelope,
        "persistence_fingerprint": hashlib.sha256(_canonical(persisted_envelope)).hexdigest(),
        "decision_eligibility_asserted": False,
    }


def test_governs_retained_audit_trail_without_deletion():
    governed = retention_report.govern_retention_authority_evidence_completeness_report_audit_trail(
        _persisted(), as_of="2026-11-18T01:00:00+00:00", retention_days=30
    )
    assert governed["retention_governance_completed"] is True
    assert governed["version"] == VERSION
    assert governed["decision_eligibility_asserted"] is False
    envelope = governed["governed"]
    assert envelope["expired"] is False
    assert envelope["retention_action"] == "RETAIN"
    assert envelope["deleted"] is False
    assert envelope["healed"] is False
    assert envelope["persistence_fingerprint"] == _persisted()["persistence_fingerprint"]
    assert envelope["enforcement_fingerprint"] == _persisted()["persisted"]["enforcement_fingerprint"]
    assert governed["retention_governance_fingerprint"] == hashlib.sha256(_canonical(envelope)).hexdigest()
    replayed = retention_report.replay_retention_authority_evidence_completeness_report_audit_trail(governed)
    assert replayed["retention_replayed"] is True
    assert replayed["expired"] is False
    assert replayed["retention_action"] == "RETAIN"
    assert replayed["deleted"] is False
    assert replayed["decision_eligibility_asserted"] is False


def test_observes_expiry_without_deletion_or_healing():
    governed = retention_report.govern_retention_authority_evidence_completeness_report_audit_trail(
        _persisted(), as_of="2026-12-18T00:00:00+00:00", retention_days=30
    )
    envelope = governed["governed"]
    assert envelope["expired"] is True
    assert envelope["retention_action"] == "EXPIRY_OBSERVED"
    assert envelope["deleted"] is False
    assert envelope["complete"] is True
    assert envelope["missing_obligations"] == []
    assert envelope["healed"] is False
    replayed = retention_report.replay_retention_authority_evidence_completeness_report_audit_trail(governed)
    assert replayed["expired"] is True
    assert replayed["retention_action"] == "EXPIRY_OBSERVED"
    assert replayed["deleted"] is False
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
def test_rejects_forbidden_retention_inputs(mutation, error):
    value = _persisted()
    mutation(value)
    with pytest.raises(Rejected) as exc:
        retention_report.govern_retention_authority_evidence_completeness_report_audit_trail(
            value, as_of="2026-11-18T01:00:00+00:00", retention_days=30
        )
    assert exc.value.args[0] == error


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda value: value.update({"point_in_time_decision": True}), "POINT_IN_TIME_DECISION"),
        (
            lambda value: value.update({"decision_eligibility_asserted": True}),
            "AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN",
        ),
        (
            lambda value: value.update({"retention_governance_completed": False}),
            "AUTHORITY_EVIDENCE_RETENTION_GOVERNANCE_INCOMPLETE",
        ),
        (
            lambda value: value.update({"retention_governance_fingerprint": "short"}),
            "AUTHORITY_EVIDENCE_RETENTION_GOVERNANCE_FINGERPRINT_INVALID",
        ),
        (
            lambda value: value.update({"retention_governance_fingerprint": "0" * 64}),
            "AUTHORITY_EVIDENCE_RETENTION_GOVERNANCE_FINGERPRINT_MISMATCH",
        ),
        (lambda value: value["governed"].update({"healed": True}), "AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"),
        (lambda value: value["governed"].update({"deleted": True}), "AUTHORITY_EVIDENCE_DELETION_FORBIDDEN"),
    ],
)
def test_rejects_forbidden_replay_inputs(mutation, error):
    value = retention_report.govern_retention_authority_evidence_completeness_report_audit_trail(
        _persisted(), as_of="2026-11-18T01:00:00+00:00", retention_days=30
    )
    mutation(value)
    with pytest.raises(Rejected) as exc:
        retention_report.replay_retention_authority_evidence_completeness_report_audit_trail(value)
    assert exc.value.args[0] == error
