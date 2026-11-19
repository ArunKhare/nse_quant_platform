"""Native authoritative evidence release readiness verification.

Verifies that the complete authoritative evidence chain is release ready while
remaining observational. Preserves all evidence fingerprints, exact replay,
immutable first-write behavior, and all safety boundaries. This module is
observational only and does not grant eligibility, live trading, healing,
backfill, adoption, deletion, production cutover, or execution authority.
POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authoritative-evidence-release-readiness-verification@1"
COMMAND = "verify.native_authoritative_evidence_release_readiness@1"
PLATFORM_VERSION = "native-authoritative-evidence-platform-acceptance-verification@1"
RELEASE_GATES = (
    "package_qa_passed",
    "integration_tests_passed",
    "operational_checks_passed",
    "evidence_chain_complete",
    "native_gates_open",
    "observational_only",
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


def _validate_platform(verified: dict[str, Any]) -> dict[str, Any]:
    if type(verified) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_VERIFIED_RESULT_REQUIRED")
    if verified.get("version") != PLATFORM_VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if verified.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if verified.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if verified.get("platform_acceptance_verification_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_PLATFORM_ACCEPTANCE_VERIFICATION_INCOMPLETE")
    envelope = verified.get("verified")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_VERIFIED_ENVELOPE_REQUIRED")
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
    fingerprint = verified.get("platform_acceptance_verification_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_PLATFORM_ACCEPTANCE_VERIFICATION_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_PLATFORM_ACCEPTANCE_VERIFICATION_FINGERPRINT_MISMATCH")
    if envelope.get("verified") is not True or envelope.get("platform_acceptance_verified") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_PLATFORM_ACCEPTANCE_VERIFICATION_INCOMPLETE")
    if envelope.get("gates_open") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_NATIVE_GATES_NOT_OPEN")
    return envelope


def verify_authoritative_evidence_release_readiness(
    verified: dict[str, Any],
    *,
    package_qa_passed: bool,
    integration_tests_passed: bool,
    operational_checks_passed: bool,
) -> dict[str, Any]:
    """Verify release readiness for the authoritative evidence chain exactly."""
    envelope = _validate_platform(verified)
    if type(package_qa_passed) is not bool or not package_qa_passed:
        raise Rejected("RELEASE_PACKAGE_QA_NOT_PASSED")
    if type(integration_tests_passed) is not bool or not integration_tests_passed:
        raise Rejected("RELEASE_INTEGRATION_TESTS_NOT_PASSED")
    if type(operational_checks_passed) is not bool or not operational_checks_passed:
        raise Rejected("RELEASE_OPERATIONAL_CHECKS_NOT_PASSED")
    release_envelope = {
        "version": VERSION,
        "platform_envelope": envelope,
        "platform_acceptance_verification_fingerprint": verified["platform_acceptance_verification_fingerprint"],
        "final_audit_id": envelope["final_audit_id"],
        "authority_id": envelope["authority_id"],
        "namespace": envelope["namespace"],
        "release_gates": list(RELEASE_GATES),
        "release_ready": True,
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
        "release_readiness_verification_completed": True,
        "version": VERSION,
        "release_ready": release_envelope,
        "release_readiness_verification_fingerprint": _sha(release_envelope),
        "decision_eligibility_asserted": False,
    }


def replay_authoritative_evidence_release_readiness_verification(
    release_ready: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay authoritative evidence release readiness verification."""
    if type(release_ready) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_RELEASE_READY_RESULT_REQUIRED")
    if release_ready.get("version") != VERSION:
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
    fingerprint = release_ready.get("release_readiness_verification_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_RELEASE_READINESS_VERIFICATION_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_RELEASE_READINESS_VERIFICATION_FINGERPRINT_MISMATCH")
    if envelope.get("release_ready") is not True or envelope.get("observational_only") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_RELEASE_READINESS_VERIFICATION_INCOMPLETE")
    return {
        "release_readiness_verification_replayed": True,
        "version": VERSION,
        "release_ready_envelope": envelope,
        "release_readiness_verification_fingerprint": fingerprint,
        "release_ready": True,
        "observational_only": True,
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
