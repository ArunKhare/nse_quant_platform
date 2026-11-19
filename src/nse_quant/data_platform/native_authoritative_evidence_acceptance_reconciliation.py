"""Native authoritative evidence acceptance and reconciliation.

Accepts and reconciles authoritative canonical identity, derivative binding,
authorized revocation, availability, and economic-validity evidence. Preserves
every evidence fingerprint and replays exactly. This module is observational
only and does not grant eligibility, live trading, healing, backfill, adoption,
deletion, or execution authority. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authoritative-evidence-acceptance-reconciliation@1"
COMMAND = "accept_reconcile.native_authoritative_evidence_acceptance_reconciliation@1"
EVIDENCE_KINDS = (
    "canonical_identity",
    "derivative_binding",
    "authorized_revocation",
    "availability",
    "economic_validity",
)
_EVIDENCE_DEFINITIONS = {
    "native-authoritative-identity-derivative-binding-revocation-evidence@1": (
        "native-authoritative-identity-derivative-binding-revocation-evidence@1",
        "record.native_authoritative_identity_derivative_binding_revocation_evidence@1",
    ),
    "native-authoritative-availability-economic-validity-evidence@1": (
        "native-authoritative-availability-economic-validity-evidence@1",
        "record.native_authoritative_availability_economic_validity_evidence@1",
    ),
}


def _pin(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _validate_evidence_result(result: dict[str, Any], kind: str) -> dict[str, Any]:
    if type(result) is not dict:
        raise Rejected("AUTHORITATIVE_EVIDENCE_RECORDED_RESULT_REQUIRED")
    if result.get("version") not in (
        "native-authoritative-identity-derivative-binding-revocation-evidence@1",
        "native-authoritative-availability-economic-validity-evidence@1",
    ):
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if result.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if result.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if result.get("recorded") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_RECORDING_INCOMPLETE")
    evidence = result.get("evidence")
    if type(evidence) is not dict:
        raise Rejected("AUTHORITATIVE_EVIDENCE_DOCUMENT_REQUIRED")
    if evidence.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    revision_id = result.get("revision_id")
    recording_fingerprint = result.get("recording_fingerprint")
    if not _pin(revision_id) or not _pin(recording_fingerprint):
        raise Rejected("EXACT_EVIDENCE_PINS_REQUIRED")
    context = _sha(evidence)
    if context != recording_fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_RECORDING_FINGERPRINT_MISMATCH")
    definition = _EVIDENCE_DEFINITIONS.get(result["version"])
    if definition is None:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    expected_revision = _sha([definition[0], definition[1], context])
    if expected_revision != revision_id:
        raise Rejected("AUTHORITY_EVIDENCE_REVISION_MISMATCH")
    if kind == "canonical_identity":
        identity = evidence.get("canonical_identity")
        if type(identity) is not dict or identity.get("identity_source") != "accepted_authority":
            raise Rejected("CANONICAL_IDENTITY_SOURCE_INVALID")
    elif kind == "derivative_binding":
        binding = evidence.get("derivative_binding")
        if type(binding) is not dict or binding.get("binding_source") != "accepted_authority":
            raise Rejected("DERIVATIVE_BINDING_SOURCE_INVALID")
    elif kind == "authorized_revocation":
        revocation = evidence.get("authorized_revocation")
        if type(revocation) is not dict or revocation.get("revocation_source") != "accepted_authority":
            raise Rejected("REVOCATION_SOURCE_INVALID")
    elif kind == "availability":
        availability = evidence.get("availability")
        if type(availability) is not dict or availability.get("source") != "accepted_authority":
            raise Rejected("AVAILABILITY_SOURCE_INVALID")
    elif kind == "economic_validity":
        economic = evidence.get("economic_validity")
        if type(economic) is not dict or economic.get("source") != "accepted_authority":
            raise Rejected("ECONOMIC_VALIDITY_SOURCE_INVALID")
    return {
        "evidence": evidence,
        "revision_id": revision_id,
        "recording_fingerprint": recording_fingerprint,
    }


def accept_and_reconcile_authoritative_evidence(
    canonical_identity: dict[str, Any],
    derivative_binding: dict[str, Any],
    authorized_revocation: dict[str, Any],
    availability: dict[str, Any],
    economic_validity: dict[str, Any],
) -> dict[str, Any]:
    """Accept and reconcile five authoritative evidence bundles exactly."""
    validated = {
        "canonical_identity": _validate_evidence_result(canonical_identity, "canonical_identity"),
        "derivative_binding": _validate_evidence_result(derivative_binding, "derivative_binding"),
        "authorized_revocation": _validate_evidence_result(authorized_revocation, "authorized_revocation"),
        "availability": _validate_evidence_result(availability, "availability"),
        "economic_validity": _validate_evidence_result(economic_validity, "economic_validity"),
    }
    authority_ids = {value["evidence"]["authority"]["authority_id"] for value in validated.values()}
    if len(authority_ids) != 1:
        raise Rejected("AUTHORITY_EVIDENCE_AUTHORITY_MISMATCH")
    accepted_envelope = {
        "version": VERSION,
        "evidence": {
            kind: {
                "evidence": value["evidence"],
                "revision_id": value["revision_id"],
                "recording_fingerprint": value["recording_fingerprint"],
            }
            for kind, value in validated.items()
        },
        "authority_id": next(iter(authority_ids)),
        "accepted": True,
        "reconciled": True,
        "evidence_kinds": list(EVIDENCE_KINDS),
        "complete": True,
        "missing_evidence_kinds": [],
        "deleted": False,
        "healed": False,
        "backfilled": False,
        "adopted": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "acceptance_reconciliation_completed": True,
        "version": VERSION,
        "accepted": accepted_envelope,
        "reconciled": accepted_envelope,
        "acceptance_reconciliation_fingerprint": _sha(accepted_envelope),
        "decision_eligibility_asserted": False,
    }


def replay_acceptance_reconciliation_authoritative_evidence(
    accepted: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay accepted and reconciled authoritative evidence without mutation."""
    if type(accepted) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_ACCEPTED_RESULT_REQUIRED")
    if accepted.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if accepted.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if accepted.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if accepted.get("acceptance_reconciliation_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_ACCEPTANCE_RECONCILIATION_INCOMPLETE")
    envelope = accepted.get("accepted")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_ACCEPTED_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    if envelope.get("deleted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_DELETION_FORBIDDEN")
    fingerprint = accepted.get("acceptance_reconciliation_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_ACCEPTANCE_RECONCILIATION_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_ACCEPTANCE_RECONCILIATION_FINGERPRINT_MISMATCH")
    if envelope.get("accepted") is not True or envelope.get("reconciled") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_ACCEPTANCE_RECONCILIATION_INCOMPLETE")
    return {
        "acceptance_reconciliation_replayed": True,
        "version": VERSION,
        "accepted_envelope": envelope,
        "acceptance_reconciliation_fingerprint": fingerprint,
        "accepted": True,
        "reconciled": True,
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
