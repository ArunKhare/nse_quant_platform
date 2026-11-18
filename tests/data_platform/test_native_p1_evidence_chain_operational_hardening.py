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
from nse_quant.data_platform.native_authoritative_evidence_chain_end_to_end_validation import (
    validate_authoritative_evidence_chain_end_to_end,
)
from nse_quant.data_platform.native_authoritative_evidence_completeness_report_audit_trail_integration import (
    integrate_authoritative_evidence_with_completeness_report_audit_trail,
)
from nse_quant.data_platform.native_authoritative_evidence_completeness_report_integration import (
    integrate_authoritative_evidence_with_completeness_report,
)
from nse_quant.data_platform.native_authoritative_evidence_decision_loop_linkage import (
    link_authoritative_evidence_to_decision_loop,
)
from nse_quant.data_platform.native_authoritative_evidence_final_audit_integration import (
    integrate_authoritative_evidence_with_final_audit,
)
from nse_quant.data_platform.native_authoritative_evidence_operational_cutover_authorization import (
    authorize_authoritative_evidence_operational_cutover,
)
from nse_quant.data_platform.native_authoritative_evidence_platform_acceptance_verification import (
    verify_authoritative_evidence_platform_acceptance,
)
from nse_quant.data_platform.native_authoritative_evidence_production_cutover_execution_authorization import (
    authorize_authoritative_evidence_production_cutover_execution,
)
from nse_quant.data_platform.native_authoritative_evidence_production_cutover_execution_completion import (
    complete_authoritative_evidence_production_cutover_execution,
)
from nse_quant.data_platform.native_authoritative_evidence_production_cutover_execution_readiness import (
    verify_authoritative_evidence_production_cutover_execution_readiness,
)
from nse_quant.data_platform.native_authoritative_evidence_production_cutover_readiness import (
    verify_authoritative_evidence_production_cutover_readiness,
)
from nse_quant.data_platform.native_authoritative_evidence_real_accepted_authority_integration import (
    integrate_authoritative_evidence_with_real_accepted_authority,
)
from nse_quant.data_platform.native_authoritative_evidence_release_readiness_verification import (
    verify_authoritative_evidence_release_readiness,
)
from nse_quant.data_platform.native_authoritative_identity_derivative_binding_revocation_evidence import (
    evidence_context as identity_context,
)
from nse_quant.data_platform.native_authoritative_identity_derivative_binding_revocation_evidence import (
    record_authoritative_identity_derivative_binding_revocation_evidence,
)
from nse_quant.data_platform.native_p1_evidence_chain_operational_hardening import (
    VERSION,
    harden_p1_evidence_chain_operations,
    replay_p1_evidence_chain_operational_hardening,
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


def _completed():
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
    integrated = integrate_authoritative_evidence_with_real_accepted_authority(
        accepted, linked, authority=_real_authority()
    )
    report = integrate_authoritative_evidence_with_completeness_report(integrated, report_id="report-001")
    audit_trail = integrate_authoritative_evidence_with_completeness_report_audit_trail(report)
    final_audit = integrate_authoritative_evidence_with_final_audit(audit_trail, final_audit_id="final-audit-001")
    validated = validate_authoritative_evidence_chain_end_to_end(final_audit)
    verified = verify_authoritative_evidence_platform_acceptance(validated)
    release_ready = verify_authoritative_evidence_release_readiness(
        verified,
        package_qa_passed=True,
        integration_tests_passed=True,
        operational_checks_passed=True,
    )
    cutover_ready = verify_authoritative_evidence_production_cutover_readiness(
        release_ready, explicit_cutover_request=True
    )
    operationally_authorized = authorize_authoritative_evidence_operational_cutover(
        cutover_ready, explicit_operational_authorization=True
    )
    execution_authorized = authorize_authoritative_evidence_production_cutover_execution(
        operationally_authorized, explicit_execution_authorization=True
    )
    execution_ready = verify_authoritative_evidence_production_cutover_execution_readiness(
        execution_authorized, explicit_readiness_request=True
    )
    return complete_authoritative_evidence_production_cutover_execution(
        execution_ready, explicit_completion_request=True
    )


def test_hardens_p1_evidence_chain_operations():
    completed = _completed()
    result = harden_p1_evidence_chain_operations(
        completed,
        health_state="healthy",
        incident_severity="informational",
        recovery_outcome="observed",
        rollback_outcome="not_required",
        observation_id="p1-observation-001",
    )
    assert result["p1_operational_hardening_completed"] is True
    assert result["version"] == VERSION
    assert result["decision_eligibility_asserted"] is False
    envelope = result["hardened"]
    assert envelope["hardened"] is True
    assert envelope["health_observed"] is True
    assert envelope["incident_observed"] is True
    assert envelope["recovery_observed"] is True
    assert envelope["rollback_observed"] is True
    assert envelope["health_state"] == "healthy"
    assert envelope["incident_severity"] == "informational"
    assert envelope["recovery_outcome"] == "observed"
    assert envelope["rollback_outcome"] == "not_required"
    assert envelope["observation_id"] == "p1-observation-001"
    assert envelope["deleted"] is False
    assert envelope["healed"] is False
    assert result["p1_operational_hardening_fingerprint"] == hashlib.sha256(_canonical(envelope)).hexdigest()
    replayed = replay_p1_evidence_chain_operational_hardening(result)
    assert replayed["p1_operational_hardening_replayed"] is True
    assert replayed["hardened"] is True
    assert replayed["deleted"] is False
    assert replayed["decision_eligibility_asserted"] is False


@pytest.mark.parametrize(
    "kwargs,error",
    [
        (
            {
                "health_state": "unknown",
                "incident_severity": "informational",
                "recovery_outcome": "observed",
                "rollback_outcome": "not_required",
                "observation_id": "p1-observation-001",
            },
            "P1_HEALTH_STATE_INVALID",
        ),
        (
            {
                "health_state": "healthy",
                "incident_severity": "unknown",
                "recovery_outcome": "observed",
                "rollback_outcome": "not_required",
                "observation_id": "p1-observation-001",
            },
            "P1_INCIDENT_SEVERITY_INVALID",
        ),
        (
            {
                "health_state": "healthy",
                "incident_severity": "informational",
                "recovery_outcome": "unknown",
                "rollback_outcome": "not_required",
                "observation_id": "p1-observation-001",
            },
            "P1_RECOVERY_OUTCOME_INVALID",
        ),
        (
            {
                "health_state": "healthy",
                "incident_severity": "informational",
                "recovery_outcome": "observed",
                "rollback_outcome": "unknown",
                "observation_id": "p1-observation-001",
            },
            "P1_ROLLBACK_OUTCOME_INVALID",
        ),
        (
            {
                "health_state": "healthy",
                "incident_severity": "informational",
                "recovery_outcome": "observed",
                "rollback_outcome": "not_required",
                "observation_id": "",
            },
            "P1_OBSERVATION_ID_REQUIRED",
        ),
    ],
)
def test_rejects_invalid_hardening_inputs(kwargs, error):
    with pytest.raises(Rejected) as exc:
        harden_p1_evidence_chain_operations(_completed(), **kwargs)
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
            lambda value: value.update({"production_cutover_execution_completed": False}),
            "AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_COMPLETION_INCOMPLETE",
        ),
        (
            lambda value: value.update({"production_cutover_execution_completion_fingerprint": "short"}),
            "AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_COMPLETION_FINGERPRINT_INVALID",
        ),
        (
            lambda value: value.update({"production_cutover_execution_completion_fingerprint": "0" * 64}),
            "AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_COMPLETION_FINGERPRINT_MISMATCH",
        ),
        (lambda value: value["completed"].update({"healed": True}), "AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"),
        (lambda value: value["completed"].update({"deleted": True}), "AUTHORITY_EVIDENCE_DELETION_FORBIDDEN"),
    ],
)
def test_rejects_forbidden_completed_inputs(mutation, error):
    value = _completed()
    mutation(value)
    with pytest.raises(Rejected) as exc:
        harden_p1_evidence_chain_operations(
            value,
            health_state="healthy",
            incident_severity="informational",
            recovery_outcome="observed",
            rollback_outcome="not_required",
            observation_id="p1-observation-001",
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
            lambda value: value.update({"p1_operational_hardening_completed": False}),
            "P1_OPERATIONAL_HARDENING_INCOMPLETE",
        ),
        (
            lambda value: value.update({"p1_operational_hardening_fingerprint": "short"}),
            "P1_OPERATIONAL_HARDENING_FINGERPRINT_INVALID",
        ),
        (
            lambda value: value.update({"p1_operational_hardening_fingerprint": "0" * 64}),
            "P1_OPERATIONAL_HARDENING_FINGERPRINT_MISMATCH",
        ),
        (lambda value: value["hardened"].update({"healed": True}), "AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"),
        (lambda value: value["hardened"].update({"deleted": True}), "AUTHORITY_EVIDENCE_DELETION_FORBIDDEN"),
    ],
)
def test_rejects_forbidden_replay_inputs(mutation, error):
    value = harden_p1_evidence_chain_operations(
        _completed(),
        health_state="healthy",
        incident_severity="informational",
        recovery_outcome="observed",
        rollback_outcome="not_required",
        observation_id="p1-observation-001",
    )
    mutation(value)
    with pytest.raises(Rejected) as exc:
        replay_p1_evidence_chain_operational_hardening(value)
    assert exc.value.args[0] == error
