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
from nse_quant.data_platform import (
    native_authority_evidence_completeness_report_audit_trail_round_trip_accept_reconcil_govern as trip_report,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _query_export():
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
        persisted, as_of="2026-11-18T01:00:00+00:00", retention_days=30
    )
    governed["version"] = "native-authority-evidence-completeness-report-audit-trail-archival-closure-governance@1"
    archival = archival_report.govern_archival_authority_evidence_completeness_report_audit_trail(
        governed, as_of="2026-11-18T02:00:00+00:00"
    )
    archival["version"] = "native-authority-evidence-completeness-report-audit-trail-query-export-governance@1"
    result = query_export_report.query_export_authority_evidence_completeness_report_audit_trail(archival)
    result["version"] = trip_report.VERSION
    return result


def test_imports_round_trips_accepts_and_reconciles():
    result = trip_report.import_round_trip_accept_reconcile_authority_evidence_compl_report_audit_trail(_query_export())
    assert result["import_round_trip_acceptance_reconciliation_completed"] is True
    assert result["version"] == trip_report.VERSION
    assert result["decision_eligibility_asserted"] is False
    envelope = result["imported"]
    assert envelope["imported"] is True
    assert envelope["round_tripped"] is True
    assert envelope["accepted"] is True
    assert envelope["reconciled"] is True
    assert envelope["complete"] is True
    assert envelope["missing_obligations"] == []
    assert envelope["deleted"] is False
    assert envelope["healed"] is False
    assert (
        result["import_round_trip_acceptance_reconciliation_fingerprint"]
        == hashlib.sha256(_canonical(envelope)).hexdigest()
    )
    replayed = trip_report.replay_import_round_trip_accept_reconcile_authority_evidence_compl_report_audit_trail(result)
    assert replayed["import_round_trip_acceptance_reconciliation_replayed"] is True
    assert replayed["imported"] is True
    assert replayed["round_tripped"] is True
    assert replayed["accepted"] is True
    assert replayed["reconciled"] is True
    assert replayed["deleted"] is False
    assert replayed["decision_eligibility_asserted"] is False


def test_preserves_incomplete_obligations_without_healing():
    value = _query_export()
    value["queried"]["missing_obligations"] = ["final_audit"]
    value["queried"]["complete"] = False
    value["queried"]["final_audit_integrated"] = False
    value["export"]["queried_envelope"] = value["queried"]
    value["export"]["query_export_fingerprint"] = hashlib.sha256(_canonical(value["queried"])).hexdigest()
    value["query_export_governance_fingerprint"] = hashlib.sha256(_canonical(value["export"])).hexdigest()
    result = trip_report.import_round_trip_accept_reconcile_authority_evidence_compl_report_audit_trail(value)
    envelope = result["imported"]
    assert envelope["complete"] is False
    assert envelope["missing_obligations"] == ["final_audit"]
    assert envelope["final_audit_integrated"] is False
    assert envelope["healed"] is False
    replayed = trip_report.replay_import_round_trip_accept_reconcile_authority_evidence_compl_report_audit_trail(result)
    assert replayed["imported_envelope"]["complete"] is False
    assert replayed["imported_envelope"]["missing_obligations"] == ["final_audit"]
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
def test_rejects_forbidden_import_inputs(mutation, error):
    value = _query_export()
    mutation(value)
    with pytest.raises(Rejected) as exc:
        trip_report.import_round_trip_accept_reconcile_authority_evidence_compl_report_audit_trail(value)
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
            lambda value: value.update({"import_round_trip_acceptance_reconciliation_completed": False}),
            "AUTHORITY_EVIDENCE_IMPORT_ROUND_TRIP_ACCEPTANCE_RECONCILIATION_INCOMPLETE",
        ),
        (
            lambda value: value.update({"import_round_trip_acceptance_reconciliation_fingerprint": "short"}),
            "AUTHORITY_EVIDENCE_IMPORT_ROUND_TRIP_ACCEPTANCE_RECONCILIATION_FINGERPRINT_INVALID",
        ),
        (
            lambda value: value.update({"import_round_trip_acceptance_reconciliation_fingerprint": "0" * 64}),
            "AUTHORITY_EVIDENCE_IMPORT_ROUND_TRIP_ACCEPTANCE_RECONCILIATION_FINGERPRINT_MISMATCH",
        ),
        (lambda value: value["imported"].update({"healed": True}), "AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"),
        (lambda value: value["imported"].update({"deleted": True}), "AUTHORITY_EVIDENCE_DELETION_FORBIDDEN"),
    ],
)
def test_rejects_forbidden_replay_inputs(mutation, error):
    value = trip_report.import_round_trip_accept_reconcile_authority_evidence_compl_report_audit_trail(_query_export())
    mutation(value)
    with pytest.raises(Rejected) as exc:
        trip_report.replay_import_round_trip_accept_reconcile_authority_evidence_compl_report_audit_trail(value)
    assert exc.value.args[0] == error
