import hashlib
import json

import pytest

from nse_quant.data_platform import (
    native_authority_evidence_completeness_report_audit_trail_archival_closure_governance as archival_report,
)
from nse_quant.data_platform import (
    native_authority_evidence_completeness_report_audit_trail_retention_expiry_governance as retention_report,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = archival_report.VERSION


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _governed(expired=False):
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
        "persisted_at": "2026-11-18T00:00:00+00:00",
        "healed": False,
        "decision_eligibility_asserted": False,
    }
    persisted = {
        "persistence_completed": True,
        "version": "native-authority-evidence-completeness-report-audit-trail-retention-expiry-governance@1",
        "persisted": persisted_envelope,
        "persistence_fingerprint": hashlib.sha256(_canonical(persisted_envelope)).hexdigest(),
        "decision_eligibility_asserted": False,
    }
    governed = retention_report.govern_retention_authority_evidence_completeness_report_audit_trail(
        persisted,
        as_of="2026-12-18T00:00:00+00:00" if expired else "2026-11-18T01:00:00+00:00",
        retention_days=30,
    )
    governed["version"] = VERSION
    return governed


def test_archives_retained_audit_trail_without_closure_or_deletion():
    archival = archival_report.govern_archival_authority_evidence_completeness_report_audit_trail(
        _governed(False), as_of="2026-11-18T02:00:00+00:00"
    )
    assert archival["archival_governance_completed"] is True
    assert archival["version"] == VERSION
    assert archival["decision_eligibility_asserted"] is False
    envelope = archival["archival_governed"]
    assert envelope["archived"] is True
    assert envelope["closed"] is False
    assert envelope["closure_status"] == "ARCHIVED"
    assert envelope["deleted"] is False
    assert envelope["healed"] is False
    assert envelope["retention_governance_fingerprint"] == _governed(False)["retention_governance_fingerprint"]
    assert archival["archival_governance_fingerprint"] == hashlib.sha256(_canonical(envelope)).hexdigest()
    replayed = archival_report.replay_archival_authority_evidence_completeness_report_audit_trail(archival)
    assert replayed["archival_replayed"] is True
    assert replayed["archived"] is True
    assert replayed["closed"] is False
    assert replayed["closure_status"] == "ARCHIVED"
    assert replayed["deleted"] is False
    assert replayed["decision_eligibility_asserted"] is False


def test_closes_expired_audit_trail_without_deletion_or_healing():
    archival = archival_report.govern_archival_authority_evidence_completeness_report_audit_trail(
        _governed(True), as_of="2026-12-18T01:00:00+00:00"
    )
    envelope = archival["archival_governed"]
    assert envelope["archived"] is True
    assert envelope["closed"] is True
    assert envelope["closure_status"] == "CLOSED"
    assert envelope["deleted"] is False
    assert envelope["complete"] is True
    assert envelope["missing_obligations"] == []
    assert envelope["healed"] is False
    replayed = archival_report.replay_archival_authority_evidence_completeness_report_audit_trail(archival)
    assert replayed["archived"] is True
    assert replayed["closed"] is True
    assert replayed["closure_status"] == "CLOSED"
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
def test_rejects_forbidden_archival_inputs(mutation, error):
    value = _governed(False)
    mutation(value)
    with pytest.raises(Rejected) as exc:
        archival_report.govern_archival_authority_evidence_completeness_report_audit_trail(
            value, as_of="2026-11-18T02:00:00+00:00"
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
            lambda value: value.update({"archival_governance_completed": False}),
            "AUTHORITY_EVIDENCE_ARCHIVAL_GOVERNANCE_INCOMPLETE",
        ),
        (
            lambda value: value.update({"archival_governance_fingerprint": "short"}),
            "AUTHORITY_EVIDENCE_ARCHIVAL_GOVERNANCE_FINGERPRINT_INVALID",
        ),
        (
            lambda value: value.update({"archival_governance_fingerprint": "0" * 64}),
            "AUTHORITY_EVIDENCE_ARCHIVAL_GOVERNANCE_FINGERPRINT_MISMATCH",
        ),
        (lambda value: value["archival_governed"].update({"healed": True}), "AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"),
        (lambda value: value["archival_governed"].update({"deleted": True}), "AUTHORITY_EVIDENCE_DELETION_FORBIDDEN"),
    ],
)
def test_rejects_forbidden_replay_inputs(mutation, error):
    value = archival_report.govern_archival_authority_evidence_completeness_report_audit_trail(
        _governed(False), as_of="2026-11-18T02:00:00+00:00"
    )
    mutation(value)
    with pytest.raises(Rejected) as exc:
        archival_report.replay_archival_authority_evidence_completeness_report_audit_trail(value)
    assert exc.value.args[0] == error
