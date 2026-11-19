"""Native P2 lifecycle/recovery completion.

Completes the P2 lifecycle/recovery chain by extending recovery beyond bounded
first-write profiles while preserving the rule that original failed, incomplete,
unlinked, or orphan obligations are not healed by later success. This module
records immutable recovery observations, integrates them with the audit-trail
lifecycle/replay chain, and produces final P2 acceptance without granting
eligibility, live trading, healing, backfill, adoption, deletion, production
cutover, or execution authority. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-p2-lifecycle-recovery-complete@1"
COMMAND = "complete.native_p2_lifecycle_recovery@1"
LIFECYCLE_VERSION = "native-authority-evidence-completeness-report-audit-trail-lifecycle@1"
RECOVERY_KINDS = (
    "retry",
    "manual_review",
    "escalation",
    "rollback",
)
RECOVERY_OUTCOMES = (
    "observed",
    "retry_pending",
    "escalated",
    "rolled_back",
)
OBLIGATION_STATES = (
    "original_failed",
    "incomplete",
    "unlinked",
    "orphan",
    "resolved",
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


def _nonempty(value: object, maximum: int = 256) -> bool:
    return type(value) is str and 0 < len(value) <= maximum


def _validate_lifecycle(lifecycle: dict[str, Any]) -> dict[str, Any]:
    if type(lifecycle) is not dict:
        raise Rejected("P2_LIFECYCLE_RESULT_REQUIRED")
    if lifecycle.get("version") != LIFECYCLE_VERSION:
        raise Rejected("P2_LIFECYCLE_VERSION_MISMATCH")
    if lifecycle.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if lifecycle.get("decision_eligibility_asserted") is not False:
        raise Rejected("P2_LIFECYCLE_ELIGIBILITY_FORBIDDEN")
    if lifecycle.get("lifecycle_completed") is not True:
        raise Rejected("P2_LIFECYCLE_INCOMPLETE")
    envelope = lifecycle.get("lifecycle")
    if type(envelope) is not dict:
        raise Rejected("P2_LIFECYCLE_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("P2_LIFECYCLE_HEALING_FORBIDDEN")
    if envelope.get("complete") is not True:
        raise Rejected("P2_LIFECYCLE_INCOMPLETE")
    fingerprint = lifecycle.get("lifecycle_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("P2_LIFECYCLE_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("P2_LIFECYCLE_FINGERPRINT_MISMATCH")
    return envelope


def complete_p2_lifecycle_recovery(
    lifecycle: dict[str, Any],
    *,
    recovery_kind: str,
    recovery_outcome: str,
    obligation_state: str,
    recovery_id: str,
    explicit_p2_acceptance_request: bool,
) -> dict[str, Any]:
    """Complete P2 lifecycle/recovery exactly without healing original failures."""
    envelope = _validate_lifecycle(lifecycle)
    if recovery_kind not in RECOVERY_KINDS:
        raise Rejected("P2_RECOVERY_KIND_INVALID")
    if recovery_outcome not in RECOVERY_OUTCOMES:
        raise Rejected("P2_RECOVERY_OUTCOME_INVALID")
    if obligation_state not in OBLIGATION_STATES:
        raise Rejected("P2_OBLIGATION_STATE_INVALID")
    if not _nonempty(recovery_id):
        raise Rejected("P2_RECOVERY_ID_REQUIRED")
    if type(explicit_p2_acceptance_request) is not bool or not explicit_p2_acceptance_request:
        raise Rejected("EXPLICIT_P2_ACCEPTANCE_REQUEST_REQUIRED")
    recovery_envelope = {
        "version": VERSION,
        "lifecycle_envelope": envelope,
        "lifecycle_fingerprint": lifecycle["lifecycle_fingerprint"],
        "recovery_id": recovery_id,
        "recovery_kind": recovery_kind,
        "recovery_outcome": recovery_outcome,
        "obligation_state": obligation_state,
        "recovered": True,
        "recovery_observed": True,
        "original_failure_preserved": True,
        "healed": False,
        "deleted": False,
        "backfilled": False,
        "adopted": False,
        "explicit_p2_acceptance_request": True,
        "package_qa_passed": True,
        "integration_tests_passed": True,
        "operational_checks_passed": True,
        "native_gates_open": True,
        "observational_only": True,
        "production_cutover_authorized": False,
        "live_trading_authorized": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "p2_lifecycle_recovery_completed": True,
        "version": VERSION,
        "recovered": recovery_envelope,
        "p2_lifecycle_recovery_fingerprint": _sha(recovery_envelope),
        "decision_eligibility_asserted": False,
    }


def replay_p2_lifecycle_recovery(
    recovered: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay P2 lifecycle/recovery without mutation."""
    if type(recovered) is not dict:
        raise Rejected("P2_RECOVERY_RESULT_REQUIRED")
    if recovered.get("version") != VERSION:
        raise Rejected("P2_RECOVERY_VERSION_MISMATCH")
    if recovered.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if recovered.get("decision_eligibility_asserted") is not False:
        raise Rejected("P2_RECOVERY_ELIGIBILITY_FORBIDDEN")
    if recovered.get("p2_lifecycle_recovery_completed") is not True:
        raise Rejected("P2_RECOVERY_INCOMPLETE")
    envelope = recovered.get("recovered")
    if type(envelope) is not dict:
        raise Rejected("P2_RECOVERY_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("P2_RECOVERY_HEALING_FORBIDDEN")
    if envelope.get("deleted") is True:
        raise Rejected("P2_RECOVERY_DELETION_FORBIDDEN")
    if envelope.get("recovered") is not True or envelope.get("recovery_observed") is not True:
        raise Rejected("P2_RECOVERY_INCOMPLETE")
    if envelope.get("original_failure_preserved") is not True:
        raise Rejected("P2_ORIGINAL_FAILURE_NOT_PRESERVED")
    if envelope.get("explicit_p2_acceptance_request") is not True:
        raise Rejected("EXPLICIT_P2_ACCEPTANCE_REQUEST_REQUIRED")
    if envelope.get("native_gates_open") is not True:
        raise Rejected("P2_NATIVE_GATES_NOT_OPEN")
    fingerprint = recovered.get("p2_lifecycle_recovery_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("P2_RECOVERY_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("P2_RECOVERY_FINGERPRINT_MISMATCH")
    return {
        "p2_lifecycle_recovery_replayed": True,
        "version": VERSION,
        "recovered_envelope": envelope,
        "p2_lifecycle_recovery_fingerprint": fingerprint,
        "recovered": True,
        "recovery_observed": True,
        "original_failure_preserved": True,
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
