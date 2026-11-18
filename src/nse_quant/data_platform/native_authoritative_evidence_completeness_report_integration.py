"""Native authoritative evidence completeness-report integration.

Integrates real accepted-authority evidence with the completeness-report
evidence chain. Preserves all evidence fingerprints, exact replay, immutable
first-write behavior, and all safety boundaries. This module is observational
only and does not grant eligibility, live trading, healing, backfill, adoption,
deletion, or execution authority. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authoritative-evidence-completeness-report-integration@1"
COMMAND = "integrate.native_authoritative_evidence_completeness_report@1"
REAL_AUTHORITY_VERSION = "native-authoritative-evidence-real-accepted-authority-integration@1"
EVIDENCE_KINDS = (
    "canonical_identity",
    "derivative_binding",
    "authorized_revocation",
    "availability",
    "economic_validity",
)
REQUIRED_OBLIGATIONS = (
    "original_first_write",
    "audit",
    "orphan_check",
    "final_audit",
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


def _validate_integrated(integrated: dict[str, Any]) -> dict[str, Any]:
    if type(integrated) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_INTEGRATED_RESULT_REQUIRED")
    if integrated.get("version") != REAL_AUTHORITY_VERSION:
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
    if envelope.get("backfilled") is True:
        raise Rejected("AUTHORITY_EVIDENCE_BACKFILL_FORBIDDEN")
    if envelope.get("adopted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_ADOPTION_FORBIDDEN")
    if envelope.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    fingerprint = integrated.get("real_accepted_authority_integration_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_REAL_ACCEPTED_AUTHORITY_INTEGRATION_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_REAL_ACCEPTED_AUTHORITY_INTEGRATION_FINGERPRINT_MISMATCH")
    if envelope.get("integrated") is not True or envelope.get("real_accepted_authority_integrated") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_REAL_ACCEPTED_AUTHORITY_INTEGRATION_INCOMPLETE")
    authority = envelope.get("authority")
    if type(authority) is not dict:
        raise Rejected("REAL_ACCEPTED_AUTHORITY_REQUIRED")
    lifecycle = authority.get("lifecycle_evidence")
    if type(lifecycle) is not dict:
        raise Rejected("REAL_ACCEPTED_AUTHORITY_LIFECYCLE_REQUIRED")
    missing = [obligation for obligation in REQUIRED_OBLIGATIONS if lifecycle.get(obligation) is not True]
    if missing:
        raise Rejected("REAL_ACCEPTED_AUTHORITY_LIFECYCLE_INCOMPLETE")
    return envelope


def integrate_authoritative_evidence_with_completeness_report(
    integrated: dict[str, Any],
    *,
    report_id: str,
) -> dict[str, Any]:
    """Integrate real accepted-authority evidence with one completeness report."""
    envelope = _validate_integrated(integrated)
    if type(report_id) is not str or not report_id:
        raise Rejected("EXACT_COMPLETENESS_REPORT_ID_REQUIRED")
    report_envelope = {
        "version": VERSION,
        "integrated_envelope": envelope,
        "real_accepted_authority_integration_fingerprint": integrated[
            "real_accepted_authority_integration_fingerprint"
        ],
        "report_id": report_id,
        "authority_id": envelope["authority_id"],
        "namespace": envelope["namespace"],
        "evidence_kinds": list(EVIDENCE_KINDS),
        "integrated": True,
        "completeness_report_integrated": True,
        "complete": envelope.get("complete") is True,
        "missing_evidence_kinds": list(envelope.get("missing_evidence_kinds", [])),
        "obligations": list(REQUIRED_OBLIGATIONS),
        "missing_obligations": [],
        "deleted": False,
        "healed": False,
        "backfilled": False,
        "adopted": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "completeness_report_integration_completed": True,
        "version": VERSION,
        "report": report_envelope,
        "completeness_report_integration_fingerprint": _sha(report_envelope),
        "decision_eligibility_asserted": False,
    }


def replay_authoritative_evidence_completeness_report_integration(
    report: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay authoritative evidence completeness-report integration."""
    if type(report) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_REPORT_RESULT_REQUIRED")
    if report.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if report.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if report.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if report.get("completeness_report_integration_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_COMPLETENESS_REPORT_INTEGRATION_INCOMPLETE")
    envelope = report.get("report")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_REPORT_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    if envelope.get("deleted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_DELETION_FORBIDDEN")
    fingerprint = report.get("completeness_report_integration_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_COMPLETENESS_REPORT_INTEGRATION_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_COMPLETENESS_REPORT_INTEGRATION_FINGERPRINT_MISMATCH")
    if envelope.get("integrated") is not True or envelope.get("completeness_report_integrated") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_COMPLETENESS_REPORT_INTEGRATION_INCOMPLETE")
    return {
        "completeness_report_integration_replayed": True,
        "version": VERSION,
        "report_envelope": envelope,
        "completeness_report_integration_fingerprint": fingerprint,
        "integrated": True,
        "completeness_report_integrated": True,
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
