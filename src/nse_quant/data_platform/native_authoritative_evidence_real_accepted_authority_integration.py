"""Native authoritative evidence real accepted-authority integration.

Integrates authoritative evidence with an independently authenticated
governance/namespace authority and real lifecycle evidence. Preserves exact
replay, immutable first-write behavior, and all safety boundaries. This module
is observational only and does not grant eligibility, live trading, healing,
backfill, adoption, deletion, or execution authority. POINT_IN_TIME_DECISION
remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authoritative-evidence-real-accepted-authority-integration@1"
COMMAND = "integrate.native_authoritative_evidence_real_accepted_authority@1"
ACCEPTANCE_VERSION = "native-authoritative-evidence-acceptance-reconciliation@1"
LINKAGE_VERSION = "native-authoritative-evidence-decision-loop-linkage@1"
EVIDENCE_KINDS = (
    "canonical_identity",
    "derivative_binding",
    "authorized_revocation",
    "availability",
    "economic_validity",
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


def _validate_authority(authority: dict[str, Any]) -> None:
    if type(authority) is not dict:
        raise Rejected("REAL_ACCEPTED_AUTHORITY_REQUIRED")
    if authority.get("authority_id") != "NSE_MASTER":
        raise Rejected("REAL_ACCEPTED_AUTHORITY_ID_INVALID")
    if authority.get("accepted") is not True:
        raise Rejected("REAL_ACCEPTED_AUTHORITY_NOT_ACCEPTED")
    if not _pin(authority.get("authority_fingerprint")):
        raise Rejected("REAL_ACCEPTED_AUTHORITY_FINGERPRINT_INVALID")
    namespace = authority.get("namespace")
    if not _nonempty(namespace):
        raise Rejected("REAL_ACCEPTED_AUTHORITY_NAMESPACE_REQUIRED")
    authenticated = authority.get("independently_authenticated")
    if authenticated is not True:
        raise Rejected("REAL_ACCEPTED_AUTHORITY_NOT_INDEPENDENTLY_AUTHENTICATED")
    lifecycle = authority.get("lifecycle_evidence")
    if type(lifecycle) is not dict:
        raise Rejected("REAL_ACCEPTED_AUTHORITY_LIFECYCLE_REQUIRED")
    if lifecycle.get("original_first_write") is not True:
        raise Rejected("REAL_ACCEPTED_AUTHORITY_ORIGINAL_FIRST_WRITE_REQUIRED")
    if lifecycle.get("audit") is not True:
        raise Rejected("REAL_ACCEPTED_AUTHORITY_AUDIT_REQUIRED")
    if lifecycle.get("orphan_check") is not True:
        raise Rejected("REAL_ACCEPTED_AUTHORITY_ORPHAN_CHECK_REQUIRED")
    if lifecycle.get("final_audit") is not True:
        raise Rejected("REAL_ACCEPTED_AUTHORITY_FINAL_AUDIT_REQUIRED")
    if lifecycle.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    if lifecycle.get("deleted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_DELETION_FORBIDDEN")
    if lifecycle.get("backfilled") is True:
        raise Rejected("AUTHORITY_EVIDENCE_BACKFILL_FORBIDDEN")
    if lifecycle.get("adopted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_ADOPTION_FORBIDDEN")


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


def _validate_linked(linked: dict[str, Any]) -> dict[str, Any]:
    if type(linked) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_LINKED_RESULT_REQUIRED")
    if linked.get("version") != LINKAGE_VERSION:
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
    return envelope


def integrate_authoritative_evidence_with_real_accepted_authority(
    accepted: dict[str, Any],
    linked: dict[str, Any],
    *,
    authority: dict[str, Any],
) -> dict[str, Any]:
    """Integrate accepted evidence and decision-loop linkage with real accepted authority."""
    accepted_envelope = _validate_accepted(accepted)
    linked_envelope = _validate_linked(linked)
    _validate_authority(authority)
    if accepted_envelope.get("authority_id") != authority["authority_id"]:
        raise Rejected("AUTHORITY_EVIDENCE_AUTHORITY_MISMATCH")
    if linked_envelope.get("authority_id") != authority["authority_id"]:
        raise Rejected("AUTHORITY_EVIDENCE_AUTHORITY_MISMATCH")
    if accepted["acceptance_reconciliation_fingerprint"] != linked_envelope["acceptance_reconciliation_fingerprint"]:
        raise Rejected("AUTHORITY_EVIDENCE_ACCEPTANCE_RECONCILIATION_FINGERPRINT_MISMATCH")
    integrated_envelope = {
        "version": VERSION,
        "accepted_envelope": accepted_envelope,
        "linked_envelope": linked_envelope,
        "acceptance_reconciliation_fingerprint": accepted["acceptance_reconciliation_fingerprint"],
        "decision_loop_linkage_fingerprint": linked["decision_loop_linkage_fingerprint"],
        "authority": authority,
        "authority_id": authority["authority_id"],
        "namespace": authority["namespace"],
        "evidence_kinds": list(EVIDENCE_KINDS),
        "integrated": True,
        "real_accepted_authority_integrated": True,
        "independently_authenticated": True,
        "lifecycle_evidence_integrated": True,
        "complete": accepted_envelope.get("complete") is True and linked_envelope.get("complete") is True,
        "missing_evidence_kinds": list(accepted_envelope.get("missing_evidence_kinds", [])),
        "deleted": False,
        "healed": False,
        "backfilled": False,
        "adopted": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "real_accepted_authority_integration_completed": True,
        "version": VERSION,
        "integrated": integrated_envelope,
        "real_accepted_authority_integration_fingerprint": _sha(integrated_envelope),
        "decision_eligibility_asserted": False,
    }


def replay_authoritative_evidence_real_accepted_authority_integration(
    integrated: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay real accepted-authority integration without mutation."""
    if type(integrated) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_INTEGRATED_RESULT_REQUIRED")
    if integrated.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if integrated.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if integrated.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if integrated.get("real_accepted_authority_integration_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_REAL_ACCEPTED_AUTHORITY_INTEGRATION_INCOMPLETE")
    envelope = integrated.get("integrated")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_INTEGRATED_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    if envelope.get("deleted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_DELETION_FORBIDDEN")
    fingerprint = integrated.get("real_accepted_authority_integration_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_REAL_ACCEPTED_AUTHORITY_INTEGRATION_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_REAL_ACCEPTED_AUTHORITY_INTEGRATION_FINGERPRINT_MISMATCH")
    if envelope.get("integrated") is not True or envelope.get("real_accepted_authority_integrated") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_REAL_ACCEPTED_AUTHORITY_INTEGRATION_INCOMPLETE")
    return {
        "real_accepted_authority_integration_replayed": True,
        "version": VERSION,
        "integrated_envelope": envelope,
        "real_accepted_authority_integration_fingerprint": fingerprint,
        "integrated": True,
        "real_accepted_authority_integrated": True,
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
