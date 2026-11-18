import hashlib
import json

import pytest

from nse_quant.data_platform.native_authoritative_availability_economic_validity_evidence import (
    evidence_context as availability_context,
)
from nse_quant.data_platform.native_authoritative_availability_economic_validity_evidence import (
    record_authoritative_availability_economic_validity_evidence,
)
from nse_quant.data_platform.native_authoritative_evidence_acceptance_reconciliation import (
    accept_and_reconcile_authoritative_evidence,
)
from nse_quant.data_platform.native_authoritative_evidence_completeness_report_integration import (
    VERSION,
    integrate_authoritative_evidence_with_completeness_report,
    replay_authoritative_evidence_completeness_report_integration,
)
from nse_quant.data_platform.native_authoritative_evidence_decision_loop_linkage import (
    link_authoritative_evidence_to_decision_loop,
)
from nse_quant.data_platform.native_authoritative_evidence_real_accepted_authority_integration import (
    integrate_authoritative_evidence_with_real_accepted_authority,
)
from nse_quant.data_platform.native_authoritative_identity_derivative_binding_revocation_evidence import (
    evidence_context as identity_context,
)
from nse_quant.data_platform.native_authoritative_identity_derivative_binding_revocation_evidence import (
    record_authoritative_identity_derivative_binding_revocation_evidence,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _authority():
    return {
        "authority_id": "NSE_MASTER",
        "accepted": True,
        "authority_fingerprint": hashlib.sha256(b"authority").hexdigest(),
    }


def _identity():
    return {
        "version": "native-authoritative-identity-derivative-binding-revocation-evidence@1",
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
        "healed": False,
        "authority": _authority(),
        "recorded_at": "2026-11-18T00:00:00+00:00",
        "knowledge_cutoff": "2026-11-18T00:00:00+00:00",
        "canonical_identity": {
            "canonical_symbol": "NIFTY",
            "identity_source": "accepted_authority",
            "identity_fingerprint": hashlib.sha256(b"identity").hexdigest(),
        },
        "derivative_binding": {
            "underlying_symbol": "NIFTY",
            "derivative_symbol": "NIFTY28NOV2026",
            "binding_source": "accepted_authority",
            "binding_fingerprint": hashlib.sha256(b"binding").hexdigest(),
        },
        "authorized_revocation": {
            "revoked": False,
            "revocation_source": "accepted_authority",
            "revocation_fingerprint": hashlib.sha256(b"revocation").hexdigest(),
            "revocation_effective_at": "2026-11-18T00:00:00+00:00",
        },
    }


def _availability():
    return {
        "version": "native-authoritative-availability-economic-validity-evidence@1",
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
        "healed": False,
        "authority": _authority(),
        "recorded_at": "2026-11-18T00:00:00+00:00",
        "knowledge_cutoff": "2026-11-18T00:00:00+00:00",
        "economic_at": "2026-11-18T01:00:00+00:00",
        "availability": {
            "available": True,
            "source": "accepted_authority",
            "revision_id": hashlib.sha256(b"availability-revision").hexdigest(),
            "recording_fingerprint": hashlib.sha256(b"availability").hexdigest(),
        },
        "economic_validity": {
            "valid": True,
            "source": "accepted_authority",
            "revision_id": hashlib.sha256(b"economic-revision").hexdigest(),
            "recording_fingerprint": hashlib.sha256(b"economic").hexdigest(),
        },
    }


def _real_authority():
    return {
        "authority_id": "NSE_MASTER",
        "accepted": True,
        "authority_fingerprint": hashlib.sha256(b"authority").hexdigest(),
        "namespace": "nse-quant/governance",
        "independently_authenticated": True,
        "lifecycle_evidence": {
            "original_first_write": True,
            "audit": True,
            "orphan_check": True,
            "final_audit": True,
            "healed": False,
            "deleted": False,
            "backfilled": False,
            "adopted": False,
        },
    }


def _integrated():
    identity = _identity()
    availability = _availability()
    identity_recorded = record_authoritative_identity_derivative_binding_revocation_evidence(
        identity, expected_context_sha256=identity_context(identity)
    )
    availability_recorded = record_authoritative_availability_economic_validity_evidence(
        availability, expected_context_sha256=availability_context(availability)
    )
    accepted = accept_and_reconcile_authoritative_evidence(
        identity_recorded, identity_recorded, identity_recorded, availability_recorded, availability_recorded
    )
    linked = link_authoritative_evidence_to_decision_loop(accepted, run_id="run-001")
    return integrate_authoritative_evidence_with_real_accepted_authority(accepted, linked, authority=_real_authority())


def test_integrates_evidence_with_completeness_report():
    integrated = _integrated()
    result = integrate_authoritative_evidence_with_completeness_report(integrated, report_id="report-001")
    assert result["completeness_report_integration_completed"] is True
    assert result["version"] == VERSION
    assert result["decision_eligibility_asserted"] is False
    envelope = result["report"]
    assert envelope["integrated"] is True
    assert envelope["completeness_report_integrated"] is True
    assert envelope["report_id"] == "report-001"
    assert envelope["authority_id"] == "NSE_MASTER"
    assert envelope["namespace"] == "nse-quant/governance"
    assert envelope["complete"] is True
    assert envelope["missing_evidence_kinds"] == []
    assert envelope["obligations"] == ["original_first_write", "audit", "orphan_check", "final_audit"]
    assert envelope["missing_obligations"] == []
    assert envelope["deleted"] is False
    assert envelope["healed"] is False
    assert result["completeness_report_integration_fingerprint"] == hashlib.sha256(_canonical(envelope)).hexdigest()
    replayed = replay_authoritative_evidence_completeness_report_integration(result)
    assert replayed["completeness_report_integration_replayed"] is True
    assert replayed["integrated"] is True
    assert replayed["completeness_report_integrated"] is True
    assert replayed["deleted"] is False
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
            lambda value: value.update({"real_accepted_authority_integration_completed": False}),
            "AUTHORITY_EVIDENCE_REAL_ACCEPTED_AUTHORITY_INTEGRATION_INCOMPLETE",
        ),
        (
            lambda value: value.update({"real_accepted_authority_integration_fingerprint": "short"}),
            "AUTHORITY_EVIDENCE_REAL_ACCEPTED_AUTHORITY_INTEGRATION_FINGERPRINT_INVALID",
        ),
        (
            lambda value: value.update({"real_accepted_authority_integration_fingerprint": "0" * 64}),
            "AUTHORITY_EVIDENCE_REAL_ACCEPTED_AUTHORITY_INTEGRATION_FINGERPRINT_MISMATCH",
        ),
        (lambda value: value["integrated"].update({"healed": True}), "AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"),
        (lambda value: value["integrated"].update({"deleted": True}), "AUTHORITY_EVIDENCE_DELETION_FORBIDDEN"),
        (
            lambda value: (
                value["integrated"]["authority"]["lifecycle_evidence"].update({"original_first_write": False}),
                value.update(
                    {
                        "real_accepted_authority_integration_fingerprint": hashlib.sha256(
                            _canonical(value["integrated"])
                        ).hexdigest()
                    }
                ),
            ),
            "REAL_ACCEPTED_AUTHORITY_LIFECYCLE_INCOMPLETE",
        ),
        (
            lambda value: (
                value["integrated"]["authority"]["lifecycle_evidence"].update({"audit": False}),
                value.update(
                    {
                        "real_accepted_authority_integration_fingerprint": hashlib.sha256(
                            _canonical(value["integrated"])
                        ).hexdigest()
                    }
                ),
            ),
            "REAL_ACCEPTED_AUTHORITY_LIFECYCLE_INCOMPLETE",
        ),
        (
            lambda value: (
                value["integrated"]["authority"]["lifecycle_evidence"].update({"orphan_check": False}),
                value.update(
                    {
                        "real_accepted_authority_integration_fingerprint": hashlib.sha256(
                            _canonical(value["integrated"])
                        ).hexdigest()
                    }
                ),
            ),
            "REAL_ACCEPTED_AUTHORITY_LIFECYCLE_INCOMPLETE",
        ),
        (
            lambda value: (
                value["integrated"]["authority"]["lifecycle_evidence"].update({"final_audit": False}),
                value.update(
                    {
                        "real_accepted_authority_integration_fingerprint": hashlib.sha256(
                            _canonical(value["integrated"])
                        ).hexdigest()
                    }
                ),
            ),
            "REAL_ACCEPTED_AUTHORITY_LIFECYCLE_INCOMPLETE",
        ),
    ],
)
def test_rejects_forbidden_integration_inputs(mutation, error):
    value = _integrated()
    mutation(value)
    with pytest.raises(Rejected) as exc:
        integrate_authoritative_evidence_with_completeness_report(value, report_id="report-001")
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
            lambda value: value.update({"completeness_report_integration_completed": False}),
            "AUTHORITY_EVIDENCE_COMPLETENESS_REPORT_INTEGRATION_INCOMPLETE",
        ),
        (
            lambda value: value.update({"completeness_report_integration_fingerprint": "short"}),
            "AUTHORITY_EVIDENCE_COMPLETENESS_REPORT_INTEGRATION_FINGERPRINT_INVALID",
        ),
        (
            lambda value: value.update({"completeness_report_integration_fingerprint": "0" * 64}),
            "AUTHORITY_EVIDENCE_COMPLETENESS_REPORT_INTEGRATION_FINGERPRINT_MISMATCH",
        ),
        (lambda value: value["report"].update({"healed": True}), "AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"),
        (lambda value: value["report"].update({"deleted": True}), "AUTHORITY_EVIDENCE_DELETION_FORBIDDEN"),
    ],
)
def test_rejects_forbidden_replay_inputs(mutation, error):
    value = integrate_authoritative_evidence_with_completeness_report(_integrated(), report_id="report-001")
    mutation(value)
    with pytest.raises(Rejected) as exc:
        replay_authoritative_evidence_completeness_report_integration(value)
    assert exc.value.args[0] == error
