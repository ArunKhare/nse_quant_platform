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
    VERSION,
    accept_and_reconcile_authoritative_evidence,
    replay_acceptance_reconciliation_authoritative_evidence,
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


def _recorded():
    identity = _identity()
    availability = _availability()
    identity_recorded = record_authoritative_identity_derivative_binding_revocation_evidence(
        identity, expected_context_sha256=identity_context(identity)
    )
    availability_recorded = record_authoritative_availability_economic_validity_evidence(
        availability, expected_context_sha256=availability_context(availability)
    )
    return identity_recorded, availability_recorded


def test_accepts_and_reconciles_all_evidence():
    identity, availability = _recorded()
    result = accept_and_reconcile_authoritative_evidence(identity, identity, identity, availability, availability)
    assert result["acceptance_reconciliation_completed"] is True
    assert result["version"] == VERSION
    assert result["decision_eligibility_asserted"] is False
    envelope = result["accepted"]
    assert envelope["accepted"] is True
    assert envelope["reconciled"] is True
    assert envelope["complete"] is True
    assert envelope["missing_evidence_kinds"] == []
    assert envelope["authority_id"] == "NSE_MASTER"
    assert envelope["deleted"] is False
    assert envelope["healed"] is False
    assert result["acceptance_reconciliation_fingerprint"] == hashlib.sha256(_canonical(envelope)).hexdigest()
    replayed = replay_acceptance_reconciliation_authoritative_evidence(result)
    assert replayed["acceptance_reconciliation_replayed"] is True
    assert replayed["accepted"] is True
    assert replayed["reconciled"] is True
    assert replayed["deleted"] is False
    assert replayed["decision_eligibility_asserted"] is False


def test_rejects_authority_mismatch():
    identity, availability = _recorded()
    availability["evidence"]["authority"]["authority_id"] = "OTHER_AUTHORITY"
    context_sha256 = hashlib.sha256(_canonical(availability["evidence"])).hexdigest()
    availability["recording_fingerprint"] = context_sha256
    availability["revision_id"] = hashlib.sha256(
        _canonical(
            [
                "native-authoritative-availability-economic-validity-evidence@1",
                "record.native_authoritative_availability_economic_validity_evidence@1",
                context_sha256,
            ]
        )
    ).hexdigest()
    with pytest.raises(Rejected) as exc:
        accept_and_reconcile_authoritative_evidence(identity, identity, identity, availability, availability)
    assert exc.value.args[0] == "AUTHORITY_EVIDENCE_AUTHORITY_MISMATCH"


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda value: value.update({"point_in_time_decision": True}), "POINT_IN_TIME_DECISION"),
        (
            lambda value: value.update({"decision_eligibility_asserted": True}),
            "AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN",
        ),
        (lambda value: value.update({"recorded": False}), "AUTHORITY_EVIDENCE_RECORDING_INCOMPLETE"),
        (lambda value: value["evidence"].update({"healed": True}), "AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"),
        (lambda value: value.update({"recording_fingerprint": "short"}), "EXACT_EVIDENCE_PINS_REQUIRED"),
    ],
)
def test_rejects_forbidden_evidence_inputs(mutation, error):
    identity, availability = _recorded()
    mutation(identity)
    with pytest.raises(Rejected) as exc:
        accept_and_reconcile_authoritative_evidence(identity, identity, identity, availability, availability)
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
def test_rejects_forbidden_replay_inputs(mutation, error):
    identity, availability = _recorded()
    value = accept_and_reconcile_authoritative_evidence(identity, identity, identity, availability, availability)
    mutation(value)
    with pytest.raises(Rejected) as exc:
        replay_acceptance_reconciliation_authoritative_evidence(value)
    assert exc.value.args[0] == error
