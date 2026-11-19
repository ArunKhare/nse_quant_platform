"""Native P3 operational acceptance completion.

Completes the P3 operational acceptance chain by evaluating multi-day,
integrated operational acceptance across package QA, integration tests,
operational checks, evidence-chain completeness, Gold/admission completion,
lifecycle/recovery completion, and exact replay. This does not grant
eligibility, live trading, healing, backfill, adoption, deletion, production
cutover, or execution authority. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-p3-operational-acceptance-complete@1"
COMMAND = "complete.native_p3_operational_acceptance@1"
MINIMUM_COMPLETE_DAYS = 3
ACCEPTANCE_DAYS = ("day_1", "day_2", "day_3")


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


def _validate_day(day: object, label: str) -> dict[str, Any]:
    if type(day) is not dict:
        raise Rejected(f"{label}_RESULT_REQUIRED")
    if day.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if day.get("decision_eligibility_asserted") is not False:
        raise Rejected(f"{label}_ELIGIBILITY_FORBIDDEN")
    if day.get("package_qa_passed") is not True:
        raise Rejected(f"{label}_PACKAGE_QA_NOT_PASSED")
    if day.get("integration_tests_passed") is not True:
        raise Rejected(f"{label}_INTEGRATION_TESTS_NOT_PASSED")
    if day.get("operational_checks_passed") is not True:
        raise Rejected(f"{label}_OPERATIONAL_CHECKS_NOT_PASSED")
    if day.get("evidence_chain_complete") is not True:
        raise Rejected(f"{label}_EVIDENCE_CHAIN_INCOMPLETE")
    if day.get("gold_admission_complete") is not True:
        raise Rejected(f"{label}_GOLD_ADMISSION_INCOMPLETE")
    if day.get("lifecycle_recovery_complete") is not True:
        raise Rejected(f"{label}_LIFECYCLE_RECOVERY_INCOMPLETE")
    if day.get("replayed") is not True:
        raise Rejected(f"{label}_REPLAY_INCOMPLETE")
    return day


def complete_p3_operational_acceptance(
    day_1: dict[str, Any],
    day_2: dict[str, Any],
    day_3: dict[str, Any],
    *,
    acceptance_id: str,
    explicit_p3_acceptance_request: bool,
) -> dict[str, Any]:
    """Complete P3 multi-day integrated operational acceptance exactly."""
    days = {
        "day_1": _validate_day(day_1, "P3_DAY_1"),
        "day_2": _validate_day(day_2, "P3_DAY_2"),
        "day_3": _validate_day(day_3, "P3_DAY_3"),
    }
    if len(days) < MINIMUM_COMPLETE_DAYS:
        raise Rejected("P3_MINIMUM_COMPLETE_DAYS_REQUIRED")
    if not _nonempty(acceptance_id):
        raise Rejected("P3_ACCEPTANCE_ID_REQUIRED")
    if type(explicit_p3_acceptance_request) is not bool or not explicit_p3_acceptance_request:
        raise Rejected("EXPLICIT_P3_ACCEPTANCE_REQUEST_REQUIRED")
    acceptance_envelope = {
        "version": VERSION,
        "acceptance_id": acceptance_id,
        "acceptance_days": list(ACCEPTANCE_DAYS),
        "day_1": days["day_1"],
        "day_2": days["day_2"],
        "day_3": days["day_3"],
        "minimum_complete_days": MINIMUM_COMPLETE_DAYS,
        "multi_day_integrated": True,
        "package_qa_passed": True,
        "integration_tests_passed": True,
        "operational_checks_passed": True,
        "evidence_chain_complete": True,
        "gold_admission_complete": True,
        "lifecycle_recovery_complete": True,
        "replayed": True,
        "accepted": True,
        "explicit_p3_acceptance_request": True,
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
        "p3_operational_acceptance_completed": True,
        "version": VERSION,
        "accepted": acceptance_envelope,
        "p3_operational_acceptance_fingerprint": _sha(acceptance_envelope),
        "decision_eligibility_asserted": False,
    }


def replay_p3_operational_acceptance(
    accepted: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay P3 operational acceptance without mutation."""
    if type(accepted) is not dict:
        raise Rejected("P3_ACCEPTANCE_RESULT_REQUIRED")
    if accepted.get("version") != VERSION:
        raise Rejected("P3_ACCEPTANCE_VERSION_MISMATCH")
    if accepted.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if accepted.get("decision_eligibility_asserted") is not False:
        raise Rejected("P3_ACCEPTANCE_ELIGIBILITY_FORBIDDEN")
    if accepted.get("p3_operational_acceptance_completed") is not True:
        raise Rejected("P3_ACCEPTANCE_INCOMPLETE")
    envelope = accepted.get("accepted")
    if type(envelope) is not dict:
        raise Rejected("P3_ACCEPTANCE_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("P3_ACCEPTANCE_HEALING_FORBIDDEN")
    if envelope.get("deleted") is True:
        raise Rejected("P3_ACCEPTANCE_DELETION_FORBIDDEN")
    if envelope.get("accepted") is not True or envelope.get("multi_day_integrated") is not True:
        raise Rejected("P3_ACCEPTANCE_INCOMPLETE")
    if envelope.get("explicit_p3_acceptance_request") is not True:
        raise Rejected("EXPLICIT_P3_ACCEPTANCE_REQUEST_REQUIRED")
    if envelope.get("native_gates_open") is not True:
        raise Rejected("P3_NATIVE_GATES_NOT_OPEN")
    fingerprint = accepted.get("p3_operational_acceptance_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("P3_ACCEPTANCE_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("P3_ACCEPTANCE_FINGERPRINT_MISMATCH")
    return {
        "p3_operational_acceptance_replayed": True,
        "version": VERSION,
        "accepted_envelope": envelope,
        "p3_operational_acceptance_fingerprint": fingerprint,
        "accepted": True,
        "multi_day_integrated": True,
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
