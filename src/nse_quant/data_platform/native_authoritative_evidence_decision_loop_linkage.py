"""Native authoritative evidence decision-loop linkage.

Links accepted and reconciled authoritative evidence to a decision-loop run
without granting eligibility, live trading, healing, backfill, adoption,
deletion, or execution authority. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authoritative-evidence-decision-loop-linkage@1"
COMMAND = "link.native_authoritative_evidence_decision_loop_linkage@1"
EVIDENCE_KINDS = (
    "canonical_identity",
    "derivative_binding",
    "authorized_revocation",
    "availability",
    "economic_validity",
)
ACCEPTANCE_VERSION = "native-authoritative-evidence-acceptance-reconciliation@1"


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


def _validate_accepted(accepted: dict[str, Any]) -> dict[str, Any]:
    if type(accepted) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_ACCEPTED_RESULT_REQUIRED")
    if accepted.get("version") != ACCEPTANCE_VERSION:
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
    if envelope.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    fingerprint = accepted.get("acceptance_reconciliation_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_ACCEPTANCE_RECONCILIATION_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_ACCEPTANCE_RECONCILIATION_FINGERPRINT_MISMATCH")
    if envelope.get("accepted") is not True or envelope.get("reconciled") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_ACCEPTANCE_RECONCILIATION_INCOMPLETE")
    evidence = envelope.get("evidence")
    if type(evidence) is not dict or set(evidence) != set(EVIDENCE_KINDS):
        raise Rejected("AUTHORITY_EVIDENCE_KINDS_INCOMPLETE")
    return envelope


def link_authoritative_evidence_to_decision_loop(
    accepted: dict[str, Any],
    *,
    run_id: str,
) -> dict[str, Any]:
    """Link accepted authoritative evidence to one decision-loop run exactly."""
    envelope = _validate_accepted(accepted)
    if not _nonempty(run_id):
        raise Rejected("EXACT_RUN_ID_REQUIRED")
    linked_envelope = {
        "version": VERSION,
        "accepted_envelope": envelope,
        "acceptance_reconciliation_fingerprint": accepted["acceptance_reconciliation_fingerprint"],
        "run_id": run_id,
        "authority_id": envelope["authority_id"],
        "evidence_kinds": list(EVIDENCE_KINDS),
        "linked": True,
        "complete": envelope.get("complete") is True,
        "missing_evidence_kinds": list(envelope.get("missing_evidence_kinds", [])),
        "decision_loop_integrated": True,
        "deleted": False,
        "healed": False,
        "backfilled": False,
        "adopted": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "decision_loop_linkage_completed": True,
        "version": VERSION,
        "linked": linked_envelope,
        "decision_loop_linkage_fingerprint": _sha(linked_envelope),
        "decision_eligibility_asserted": False,
    }


def replay_authoritative_evidence_decision_loop_linkage(
    linked: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay authoritative evidence decision-loop linkage without mutation."""
    if type(linked) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_LINKED_RESULT_REQUIRED")
    if linked.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if linked.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if linked.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if linked.get("decision_loop_linkage_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_DECISION_LOOP_LINKAGE_INCOMPLETE")
    envelope = linked.get("linked")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_LINKED_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    if envelope.get("deleted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_DELETION_FORBIDDEN")
    fingerprint = linked.get("decision_loop_linkage_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_DECISION_LOOP_LINKAGE_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_DECISION_LOOP_LINKAGE_FINGERPRINT_MISMATCH")
    if envelope.get("linked") is not True or envelope.get("decision_loop_integrated") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_DECISION_LOOP_LINKAGE_INCOMPLETE")
    return {
        "decision_loop_linkage_replayed": True,
        "version": VERSION,
        "linked_envelope": envelope,
        "decision_loop_linkage_fingerprint": fingerprint,
        "linked": True,
        "decision_loop_integrated": True,
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
