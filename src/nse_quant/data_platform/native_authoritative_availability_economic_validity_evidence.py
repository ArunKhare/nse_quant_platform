"""Native authoritative availability and economic-validity evidence.

Records independently sourced availability and economic-validity evidence from
accepted authorities. Records are immutable first-write evidence and replay
exactly. This module is observational only and does not grant eligibility, live
trading, healing, backfill, adoption, deletion, or execution authority.
POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authoritative-availability-economic-validity-evidence@1"
COMMAND = "record.native_authoritative_availability_economic_validity_evidence@1"
EVIDENCE_KINDS = (
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


def _iso(value: object) -> bool:
    if type(value) is not str or not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _nonempty(value: object, maximum: int = 256) -> bool:
    return type(value) is str and 0 < len(value) <= maximum


def _validate_evidence(evidence: dict[str, Any]) -> None:
    if type(evidence) is not dict:
        raise Rejected("AUTHORITATIVE_AVAILABILITY_ECONOMIC_EVIDENCE_REQUIRED")
    if evidence.get("version") != VERSION:
        raise Rejected("AUTHORITATIVE_AVAILABILITY_ECONOMIC_EVIDENCE_VERSION_MISMATCH")
    if evidence.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if evidence.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITATIVE_AVAILABILITY_ECONOMIC_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if evidence.get("healed") is True:
        raise Rejected("AUTHORITATIVE_AVAILABILITY_ECONOMIC_EVIDENCE_HEALING_FORBIDDEN")
    authority = evidence.get("authority")
    if type(authority) is not dict:
        raise Rejected("ACCEPTED_AUTHORITY_REQUIRED")
    if not _nonempty(authority.get("authority_id")):
        raise Rejected("AUTHORITY_ID_REQUIRED")
    if authority.get("accepted") is not True:
        raise Rejected("AUTHORITY_NOT_ACCEPTED")
    if not _pin(authority.get("authority_fingerprint")):
        raise Rejected("AUTHORITY_FINGERPRINT_INVALID")
    if not _iso(evidence.get("recorded_at")):
        raise Rejected("RECORDED_AT_REQUIRED")
    if not _iso(evidence.get("knowledge_cutoff")):
        raise Rejected("KNOWLEDGE_CUTOFF_REQUIRED")
    if not _iso(evidence.get("economic_at")):
        raise Rejected("ECONOMIC_AT_REQUIRED")
    if evidence.get("knowledge_cutoff") == evidence.get("economic_at"):
        raise Rejected("SEPARATE_TIME_AXES_REQUIRED")
    availability = evidence.get("availability")
    if type(availability) is not dict:
        raise Rejected("AVAILABILITY_EVIDENCE_REQUIRED")
    if availability.get("available") is not True:
        raise Rejected("AVAILABILITY_NOT_ASSERTED")
    if availability.get("source") != "accepted_authority":
        raise Rejected("AVAILABILITY_SOURCE_INVALID")
    if not _pin(availability.get("revision_id")):
        raise Rejected("AVAILABILITY_REVISION_INVALID")
    if not _pin(availability.get("recording_fingerprint")):
        raise Rejected("AVAILABILITY_FINGERPRINT_INVALID")
    economic = evidence.get("economic_validity")
    if type(economic) is not dict:
        raise Rejected("ECONOMIC_VALIDITY_EVIDENCE_REQUIRED")
    if economic.get("valid") is not True:
        raise Rejected("ECONOMIC_VALIDITY_NOT_ASSERTED")
    if economic.get("source") != "accepted_authority":
        raise Rejected("ECONOMIC_VALIDITY_SOURCE_INVALID")
    if not _pin(economic.get("revision_id")):
        raise Rejected("ECONOMIC_VALIDITY_REVISION_INVALID")
    if not _pin(economic.get("recording_fingerprint")):
        raise Rejected("ECONOMIC_VALIDITY_FINGERPRINT_INVALID")


def evidence_context(evidence: dict[str, Any]) -> str:
    """Return the exact canonical SHA-256 context for authoritative evidence."""
    _validate_evidence(evidence)
    return _sha(evidence)


def record_authoritative_availability_economic_validity_evidence(
    evidence: dict[str, Any],
    *,
    expected_context_sha256: str,
) -> dict[str, Any]:
    """Record one immutable authoritative availability/economic-validity bundle."""
    _validate_evidence(evidence)
    if not _pin(expected_context_sha256):
        raise Rejected("EXACT_EXPECTED_CONTEXT_PIN_REQUIRED")
    context = _sha(evidence)
    if context != expected_context_sha256:
        raise Rejected("REVIEWED_AUTHORITATIVE_AVAILABILITY_ECONOMIC_CONTEXT_CHANGED")
    revision_id = _sha([VERSION, COMMAND, context])
    return {
        "recorded": True,
        "version": VERSION,
        "revision_id": revision_id,
        "recording_fingerprint": context,
        "evidence": evidence,
        "evidence_kinds": list(EVIDENCE_KINDS),
        "immutable": True,
        "healed": False,
        "backfilled": False,
        "adopted": False,
        "deleted": False,
        "decision_eligibility_asserted": False,
    }


def replay_authoritative_availability_economic_validity_evidence(
    recorded: dict[str, Any],
    *,
    expected_revision_id: str,
    expected_recording_fingerprint: str,
) -> dict[str, Any]:
    """Exactly replay recorded authoritative evidence without mutation."""
    if type(recorded) is not dict:
        raise Rejected("AUTHORITATIVE_AVAILABILITY_ECONOMIC_RECORDED_RESULT_REQUIRED")
    if recorded.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if recorded.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if recorded.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if recorded.get("recorded") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_RECORDING_INCOMPLETE")
    evidence = recorded.get("evidence")
    if type(evidence) is not dict:
        raise Rejected("AUTHORITATIVE_AVAILABILITY_ECONOMIC_EVIDENCE_REQUIRED")
    if evidence.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    if not _pin(expected_revision_id) or not _pin(expected_recording_fingerprint):
        raise Rejected("EXACT_EVIDENCE_PINS_REQUIRED")
    if recorded.get("revision_id") != expected_revision_id:
        raise Rejected("AUTHORITY_EVIDENCE_REVISION_MISMATCH")
    context = _sha(evidence)
    if context != expected_recording_fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_RECORDING_FINGERPRINT_MISMATCH")
    expected_revision = _sha([VERSION, COMMAND, context])
    if expected_revision != expected_revision_id:
        raise Rejected("AUTHORITY_EVIDENCE_REVISION_MISMATCH")
    _validate_evidence(evidence)
    return {
        "replayed": True,
        "version": VERSION,
        "revision_id": expected_revision_id,
        "recording_fingerprint": expected_recording_fingerprint,
        "evidence": evidence,
        "evidence_kinds": list(EVIDENCE_KINDS),
        "immutable": True,
        "healed": False,
        "backfilled": False,
        "adopted": False,
        "deleted": False,
        "decision_eligibility_asserted": False,
    }
