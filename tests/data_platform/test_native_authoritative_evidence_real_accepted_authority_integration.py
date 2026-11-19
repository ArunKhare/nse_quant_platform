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
from nse_quant.data_platform.native_authoritative_evidence_decision_loop_linkage import (
    link_authoritative_evidence_to_decision_loop,
)
from nse_quant.data_platform.native_authoritative_evidence_real_accepted_authority_integration import (
    VERSION,
    integrate_authoritative_evidence_with_real_accepted_authority,
    replay_authoritative_evidence_real_accepted_authority_integration,
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


def _accepted_and_linked():
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
    return accepted, linked


def test_integrates_real_accepted_authority():
    accepted, linked = _accepted_and_linked()
    result = integrate_authoritative_evidence_with_real_accepted_authority(
        accepted, linked, authority=_real_authority()
    )
    assert result["real_accepted_authority_integration_completed"] is True
    assert result["version"] == VERSION
    assert result["decision_eligibility_asserted"] is False
    envelope = result["integrated"]
    assert envelope["integrated"] is True
    assert envelope["real_accepted_authority_integrated"] is True
    assert envelope["independently_authenticated"] is True
    assert envelope["lifecycle_evidence_integrated"] is True
    assert envelope["authority_id"] == "NSE_MASTER"
    assert envelope["namespace"] == "nse-quant/governance"
    assert envelope["complete"] is True
    assert envelope["missing_evidence_kinds"] == []
    assert envelope["deleted"] is False
    assert envelope["healed"] is False
    assert result["real_accepted_authority_integration_fingerprint"] == hashlib.sha256(_canonical(envelope)).hexdigest()
    replayed = replay_authoritative_evidence_real_accepted_authority_integration(result)
    assert replayed["real_accepted_authority_integration_replayed"] is True
    assert replayed["integrated"] is True
    assert replayed["real_accepted_authority_integrated"] is True
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
            lambda value: value.update({"acceptance_reconciliation_completed": False}),
            "AUTHORITY_EVIDENCE_ACCEPTANCE_RECONCILIATION_INCOMPLETE",
        ),
        (
            lambda value: value.update({"acceptance_reconciliation_fingerprint": "short"}),
            "AUTHORITY_EVIDENCE_ACCEPTANCE_RECONCILIATION_FINGERPRINT_INVALID",
        ),
        (
            lambda value: value.update({"acceptance_reconciliation_fingerprint": "0" * 64}),
            "AUTHORITY_EVIDENCE_ACCEPTANCE_RECONCILIATION_FINGERPRINT_MISMATCH",
        ),
        (lambda value: value["accepted"].update({"healed": True}), "AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"),
        (lambda value: value["accepted"].update({"deleted": True}), "AUTHORITY_EVIDENCE_DELETION_FORBIDDEN"),
    ],
)
def test_rejects_forbidden_accepted_inputs(mutation, error):
    accepted, linked = _accepted_and_linked()
    mutation(accepted)
    with pytest.raises(Rejected) as exc:
        integrate_authoritative_evidence_with_real_accepted_authority(accepted, linked, authority=_real_authority())
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
            lambda value: value.update({"decision_loop_linkage_completed": False}),
            "AUTHORITY_EVIDENCE_DECISION_LOOP_LINKAGE_INCOMPLETE",
        ),
        (
            lambda value: value.update({"decision_loop_linkage_fingerprint": "short"}),
            "AUTHORITY_EVIDENCE_DECISION_LOOP_LINKAGE_FINGERPRINT_INVALID",
        ),
        (
            lambda value: value.update({"decision_loop_linkage_fingerprint": "0" * 64}),
            "AUTHORITY_EVIDENCE_DECISION_LOOP_LINKAGE_FINGERPRINT_MISMATCH",
        ),
        (lambda value: value["linked"].update({"healed": True}), "AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"),
        (lambda value: value["linked"].update({"deleted": True}), "AUTHORITY_EVIDENCE_DELETION_FORBIDDEN"),
    ],
)
def test_rejects_forbidden_linked_inputs(mutation, error):
    accepted, linked = _accepted_and_linked()
    mutation(linked)
    with pytest.raises(Rejected) as exc:
        integrate_authoritative_evidence_with_real_accepted_authority(accepted, linked, authority=_real_authority())
    assert exc.value.args[0] == error


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda value: value.update({"authority_id": "OTHER_AUTHORITY"}), "REAL_ACCEPTED_AUTHORITY_ID_INVALID"),
        (lambda value: value.update({"accepted": False}), "REAL_ACCEPTED_AUTHORITY_NOT_ACCEPTED"),
        (lambda value: value.update({"authority_fingerprint": "short"}), "REAL_ACCEPTED_AUTHORITY_FINGERPRINT_INVALID"),
        (lambda value: value.update({"namespace": ""}), "REAL_ACCEPTED_AUTHORITY_NAMESPACE_REQUIRED"),
        (
            lambda value: value.update({"independently_authenticated": False}),
            "REAL_ACCEPTED_AUTHORITY_NOT_INDEPENDENTLY_AUTHENTICATED",
        ),
        (
            lambda value: value["lifecycle_evidence"].update({"original_first_write": False}),
            "REAL_ACCEPTED_AUTHORITY_ORIGINAL_FIRST_WRITE_REQUIRED",
        ),
        (lambda value: value["lifecycle_evidence"].update({"audit": False}), "REAL_ACCEPTED_AUTHORITY_AUDIT_REQUIRED"),
        (
            lambda value: value["lifecycle_evidence"].update({"orphan_check": False}),
            "REAL_ACCEPTED_AUTHORITY_ORPHAN_CHECK_REQUIRED",
        ),
        (
            lambda value: value["lifecycle_evidence"].update({"final_audit": False}),
            "REAL_ACCEPTED_AUTHORITY_FINAL_AUDIT_REQUIRED",
        ),
        (lambda value: value["lifecycle_evidence"].update({"healed": True}), "AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"),
        (lambda value: value["lifecycle_evidence"].update({"deleted": True}), "AUTHORITY_EVIDENCE_DELETION_FORBIDDEN"),
    ],
)
def test_rejects_forbidden_authority_inputs(mutation, error):
    accepted, linked = _accepted_and_linked()
    authority = _real_authority()
    mutation(authority)
    with pytest.raises(Rejected) as exc:
        integrate_authoritative_evidence_with_real_accepted_authority(accepted, linked, authority=authority)
    assert exc.value.args[0] == error
