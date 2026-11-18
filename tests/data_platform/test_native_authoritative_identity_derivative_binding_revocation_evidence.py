import hashlib
import json

import pytest

from nse_quant.data_platform.native_authoritative_identity_derivative_binding_revocation_evidence import (
    VERSION,
    evidence_context,
    record_authoritative_identity_derivative_binding_revocation_evidence,
    replay_authoritative_identity_derivative_binding_revocation_evidence,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _evidence():
    return {
        "version": VERSION,
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
        "healed": False,
        "authority": {
            "authority_id": "NSE_MASTER",
            "accepted": True,
            "authority_fingerprint": hashlib.sha256(b"authority").hexdigest(),
        },
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


def test_records_and_replays_authoritative_evidence_exactly():
    evidence = _evidence()
    context = evidence_context(evidence)
    recorded = record_authoritative_identity_derivative_binding_revocation_evidence(
        evidence, expected_context_sha256=context
    )
    assert recorded["recorded"] is True
    assert recorded["version"] == VERSION
    assert recorded["recording_fingerprint"] == context
    assert recorded["immutable"] is True
    assert recorded["healed"] is False
    assert recorded["decision_eligibility_asserted"] is False
    replayed = replay_authoritative_identity_derivative_binding_revocation_evidence(
        recorded,
        expected_revision_id=recorded["revision_id"],
        expected_recording_fingerprint=context,
    )
    assert replayed["replayed"] is True
    assert replayed["evidence"] == evidence
    assert replayed["recording_fingerprint"] == context
    assert replayed["decision_eligibility_asserted"] is False


def test_rejects_context_change_without_healing():
    evidence = _evidence()
    context = evidence_context(evidence)
    evidence["canonical_identity"]["canonical_symbol"] = "BANKNIFTY"
    with pytest.raises(Rejected) as exc:
        record_authoritative_identity_derivative_binding_revocation_evidence(evidence, expected_context_sha256=context)
    assert exc.value.args[0] == "REVIEWED_AUTHORITATIVE_CONTEXT_CHANGED"


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda value: value.update({"point_in_time_decision": True}), "POINT_IN_TIME_DECISION"),
        (
            lambda value: value.update({"decision_eligibility_asserted": True}),
            "AUTHORITATIVE_EVIDENCE_ELIGIBILITY_FORBIDDEN",
        ),
        (lambda value: value.update({"healed": True}), "AUTHORITATIVE_EVIDENCE_HEALING_FORBIDDEN"),
        (lambda value: value["authority"].update({"accepted": False}), "AUTHORITY_NOT_ACCEPTED"),
        (lambda value: value["authority"].update({"authority_fingerprint": "short"}), "AUTHORITY_FINGERPRINT_INVALID"),
        (
            lambda value: value["canonical_identity"].update({"identity_source": "provider"}),
            "CANONICAL_IDENTITY_SOURCE_INVALID",
        ),
        (
            lambda value: value["derivative_binding"].update({"binding_source": "provider"}),
            "DERIVATIVE_BINDING_SOURCE_INVALID",
        ),
        (
            lambda value: value["authorized_revocation"].update({"revocation_source": "provider"}),
            "REVOCATION_SOURCE_INVALID",
        ),
    ],
)
def test_rejects_forbidden_evidence(mutation, error):
    evidence = _evidence()
    mutation(evidence)
    with pytest.raises(Rejected) as exc:
        evidence_context(evidence)
    assert exc.value.args[0] == error


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda value: value.update({"point_in_time_decision": True}), "POINT_IN_TIME_DECISION"),
        (
            lambda value: value.update({"decision_eligibility_asserted": True}),
            "AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN",
        ),
        (lambda value: value.update({"recorded": False}), "AUTHORITY_EVIDENCE_RECORDING_INCOMPLETE"),
        (lambda value: value.update({"revision_id": "short"}), "EXACT_EVIDENCE_PINS_REQUIRED"),
        (lambda value: value.update({"revision_id": "0" * 64}), "AUTHORITY_EVIDENCE_REVISION_MISMATCH"),
        (lambda value: value["evidence"].update({"healed": True}), "AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"),
    ],
)
def test_rejects_forbidden_replay_inputs(mutation, error):
    evidence = _evidence()
    context = evidence_context(evidence)
    recorded = record_authoritative_identity_derivative_binding_revocation_evidence(
        evidence, expected_context_sha256=context
    )
    mutation(recorded)
    with pytest.raises(Rejected) as exc:
        replay_authoritative_identity_derivative_binding_revocation_evidence(
            recorded,
            expected_revision_id=recorded["revision_id"],
            expected_recording_fingerprint=context,
        )
    assert exc.value.args[0] == error
