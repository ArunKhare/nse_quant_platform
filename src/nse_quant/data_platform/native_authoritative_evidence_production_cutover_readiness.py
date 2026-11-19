"""Native authoritative evidence production cutover readiness.

Verifies that the complete authoritative evidence chain is production cutover
ready while remaining observational. Requires explicit release readiness and
does not grant eligibility, live trading, healing, backfill, adoption, deletion,
production cutover, or execution authority. POINT_IN_TIME_DECISION remains
rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authoritative-evidence-production-cutover-readiness@1"
COMMAND = "verify.native_authoritative_evidence_production_cutover_readiness@1"
RELEASE_VERSION = "native-authoritative-evidence-release-readiness-verification@1"
CUTOVER_GATES = (
    "release_ready",
    "package_qa_passed",
    "integration_tests_passed",
    "operational_checks_passed",
    "evidence_chain_complete",
    "native_gates_open",
    "observational_only",
    "explicit_cutover_request",
)


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


def _validate_release_ready(release_ready: dict[str, Any]) -> dict[str, Any]:
    if type(release_ready) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_RELEASE_READY_RESULT_REQUIRED")
    if release_ready.get("version") != RELEASE_VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if release_ready.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if release_ready.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if release_ready.get("release_readiness_verification_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_RELEASE_READINESS_VERIFICATION_INCOMPLETE")
    envelope = release_ready.get("release_ready")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_RELEASE_READY_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    if envelope.get("deleted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_DELETION_FORBIDDEN")
    if envelope.get("backfilled") is True:
        raise Rejected("AUTHORITY_EVIDENCE_BACKFILL_FORBIDDEN")
    if envelope.get("adopted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_ADOPTION_FORBIDDEN")
    if envelope.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    fingerprint = release_ready.get("release_readiness_verification_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_RELEASE_READINESS_VERIFICATION_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_RELEASE_READINESS_VERIFICATION_FINGERPRINT_MISMATCH")
    if envelope.get("release_ready") is not True or envelope.get("observational_only") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_RELEASE_READINESS_VERIFICATION_INCOMPLETE")
    if envelope.get("native_gates_open") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_NATIVE_GATES_NOT_OPEN")
    return envelope


def verify_authoritative_evidence_production_cutover_readiness(
    release_ready: dict[str, Any],
    *,
    explicit_cutover_request: bool,
) -> dict[str, Any]:
    """Verify production cutover readiness for the authoritative evidence chain exactly."""
    envelope = _validate_release_ready(release_ready)
    if type(explicit_cutover_request) is not bool or not explicit_cutover_request:
        raise Rejected("EXPLICIT_CUTOVER_REQUEST_REQUIRED")
    cutover_envelope = {
        "version": VERSION,
        "release_ready_envelope": envelope,
        "release_readiness_verification_fingerprint": release_ready["release_readiness_verification_fingerprint"],
        "final_audit_id": envelope["final_audit_id"],
        "authority_id": envelope["authority_id"],
        "namespace": envelope["namespace"],
        "cutover_gates": list(CUTOVER_GATES),
        "cutover_ready": True,
        "explicit_cutover_request": True,
        "package_qa_passed": True,
        "integration_tests_passed": True,
        "operational_checks_passed": True,
        "evidence_chain_complete": True,
        "native_gates_open": True,
        "observational_only": True,
        "production_cutover_authorized": False,
        "live_trading_authorized": False,
        "deleted": False,
        "healed": False,
        "backfilled": False,
        "adopted": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "production_cutover_readiness_completed": True,
        "version": VERSION,
        "cutover_ready": cutover_envelope,
        "production_cutover_readiness_fingerprint": _sha(cutover_envelope),
        "decision_eligibility_asserted": False,
    }


def replay_authoritative_evidence_production_cutover_readiness(
    cutover_ready: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay authoritative evidence production cutover readiness."""
    if type(cutover_ready) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_CUTOVER_READY_RESULT_REQUIRED")
    if cutover_ready.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if cutover_ready.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if cutover_ready.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if cutover_ready.get("production_cutover_readiness_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_READINESS_INCOMPLETE")
    envelope = cutover_ready.get("cutover_ready")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_CUTOVER_READY_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    if envelope.get("deleted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_DELETION_FORBIDDEN")
    fingerprint = cutover_ready.get("production_cutover_readiness_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_READINESS_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_READINESS_FINGERPRINT_MISMATCH")
    if envelope.get("cutover_ready") is not True or envelope.get("observational_only") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_READINESS_INCOMPLETE")
    return {
        "production_cutover_readiness_replayed": True,
        "version": VERSION,
        "cutover_ready_envelope": envelope,
        "production_cutover_readiness_fingerprint": fingerprint,
        "cutover_ready": True,
        "observational_only": True,
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
