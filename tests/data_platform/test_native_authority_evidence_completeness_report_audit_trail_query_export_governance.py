import hashlib
import json

import pytest

from nse_quant.data_platform import (
    native_authority_evidence_completeness_report_audit_trail_archival_closure_governance as archival_report,
)
from nse_quant.data_platform import (
    native_authority_evidence_completeness_report_audit_trail_query_export_governance as query_export_report,
)
from nse_quant.data_platform import (
    native_authority_evidence_completeness_report_audit_trail_retention_expiry_governance as retention_report,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _archival(expired=False):
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
    governed = govern_retention(persisted, expired)
    archival = archival_report.govern_archival_authority_evidence_completeness_report_audit_trail(
        governed, as_of="2026-12-18T01:00:00+00:00" if expired else "2026-11-18T02:00:00+00:00"
    )
    archival["version"] = "native-authority-evidence-completeness-report-audit-trail-query-export-governance@1"
    return archival


def govern_retention(persisted, expired):
    governed = retention_report.govern_retention_authority_evidence_completeness_report_audit_trail(
        persisted,
        as_of="2026-12-18T00:00:00+00:00" if expired else "2026-11-18T01:00:00+00:00",
        retention_days=30,
    )
    governed["version"] = "native-authority-evidence-completeness-report-audit-trail-archival-closure-governance@1"
    return governed


def test_queries_and_exports_archived_audit_trail():
    result = query_export_report.query_export_authority_evidence_completeness_report_audit_trail(_archival(False))
    assert result["query_export_completed"] is True
    assert result["version"] == query_export_report.VERSION
    assert result["decision_eligibility_asserted"] is False
    queried = result["queried"]
    assert queried["queried"] is True
    assert queried["exported"] is True
    assert queried["archived"] is True
    assert queried["closed"] is False
    assert queried["closure_status"] == "ARCHIVED"
    assert queried["deleted"] is False
    assert queried["healed"] is False
    assert result["query_export_governance_fingerprint"] == hashlib.sha256(_canonical(result["export"])).hexdigest()
    replayed = query_export_report.replay_query_export_authority_evidence_completeness_report_audit_trail(result)
    assert replayed["query_export_replayed"] is True
    assert replayed["queried_envelope"] == queried
    assert replayed["export_envelope"] == result["export"]
    assert replayed["deleted"] is False
    assert replayed["decision_eligibility_asserted"] is False


def test_queries_and_exports_closed_audit_trail():
    result = query_export_report.query_export_authority_evidence_completeness_report_audit_trail(_archival(True))
    queried = result["queried"]
    assert queried["closed"] is True
    assert queried["closure_status"] == "CLOSED"
    assert queried["deleted"] is False
    assert queried["complete"] is True
    assert queried["missing_obligations"] == []
    replayed = query_export_report.replay_query_export_authority_evidence_completeness_report_audit_trail(result)
    assert replayed["query_export_replayed"] is True
    assert replayed["queried_envelope"]["closed"] is True
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
def test_rejects_forbidden_query_export_inputs(mutation, error):
    value = _archival(False)
    mutation(value)
    with pytest.raises(Rejected) as exc:
        query_export_report.query_export_authority_evidence_completeness_report_audit_trail(value)
    assert exc.value.args[0] == error


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda value: value.update({"point_in_time_decision": True}), "POINT_IN_TIME_DECISION"),
        (
            lambda value: value.update({"decision_eligibility_asserted": True}),
            "AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN",
        ),
        (lambda value: value.update({"query_export_completed": False}), "AUTHORITY_EVIDENCE_QUERY_EXPORT_INCOMPLETE"),
        (
            lambda value: value.update({"query_export_governance_fingerprint": "short"}),
            "AUTHORITY_EVIDENCE_QUERY_EXPORT_GOVERNANCE_FINGERPRINT_INVALID",
        ),
        (
            lambda value: value.update({"query_export_governance_fingerprint": "0" * 64}),
            "AUTHORITY_EVIDENCE_QUERY_EXPORT_GOVERNANCE_FINGERPRINT_MISMATCH",
        ),
        (lambda value: value["export"].update({"healed": True}), "AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"),
        (lambda value: value["export"].update({"deleted": True}), "AUTHORITY_EVIDENCE_DELETION_FORBIDDEN"),
    ],
)
def test_rejects_forbidden_replay_inputs(mutation, error):
    value = query_export_report.query_export_authority_evidence_completeness_report_audit_trail(_archival(False))
    mutation(value)
    with pytest.raises(Rejected) as exc:
        query_export_report.replay_query_export_authority_evidence_completeness_report_audit_trail(value)
    assert exc.value.args[0] == error
