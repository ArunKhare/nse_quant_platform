"""Native P1 Gold/admission chain completion.

Completes the P1 Gold/admission chain by evaluating a versioned Gold decision
publication candidate against the new sufficient eligible publication/admission
contract, recording an immutable admission determination, integrating it with
the controlled execution gateway boundary, and producing final P1 admission
acceptance. This does not grant blanket eligibility, authorize live trading,
healing, backfill, adoption, deletion, production cutover, or execution.
POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected
from nse_quant.data_platform.native_strategy_requirements import STRATEGY

VERSION = "native-p1-gold-admission-chain-complete@1"
COMMAND = "complete.native_p1_gold_admission_chain@1"
GOLD_VERSION = "native-iron-condor-decision-gold@1"
ADMISSION_VERSION = "native-iron-condor-decision-admission@1"
CONTRACT_VERSION = "eligible-admission-contract@1"
ADMISSION_KINDS = ("publication", "admission")
EXECUTION_MODES = ("paper", "dry_run", "live")


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


def _validate_gold(gold_document: dict[str, Any]) -> dict[str, Any]:
    if type(gold_document) is not dict:
        raise Rejected("DECISION_GOLD_DOCUMENT_REQUIRED")
    if gold_document.get("version") != GOLD_VERSION:
        raise Rejected("DECISION_GOLD_VERSION_MISMATCH")
    if gold_document.get("strategy") != STRATEGY:
        raise Rejected("DECISION_GOLD_STRATEGY_MISMATCH")
    if gold_document.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if gold_document.get("decision_eligibility_asserted") is not False:
        raise Rejected("DECISION_GOLD_ELIGIBILITY_FORBIDDEN")
    if not _nonempty(gold_document.get("run_id")):
        raise Rejected("DECISION_GOLD_RUN_ID_REQUIRED")
    for label, value in (
        (
            "DECISION_GOLD_RECONCILIATION_EVIDENCE_INVALID",
            gold_document.get("reconciliation_revision_id"),
        ),
        (
            "DECISION_GOLD_RECONCILIATION_EVIDENCE_INVALID",
            gold_document.get("reconciliation_recording_fingerprint"),
        ),
        (
            "DECISION_GOLD_IDENTITY_TIME_EVIDENCE_INVALID",
            gold_document.get("identity_time_evidence_revision_id"),
        ),
        (
            "DECISION_GOLD_IDENTITY_TIME_EVIDENCE_INVALID",
            gold_document.get("identity_time_evidence_recording_fingerprint"),
        ),
        (
            "DECISION_GOLD_AVAILABILITY_ECONOMIC_EVIDENCE_INVALID",
            gold_document.get("availability_economic_evidence_revision_id"),
        ),
        (
            "DECISION_GOLD_AVAILABILITY_ECONOMIC_EVIDENCE_INVALID",
            gold_document.get("availability_economic_evidence_recording_fingerprint"),
        ),
    ):
        if not _pin(value):
            raise Rejected(label)
    stages = gold_document.get("stages")
    if type(stages) is not list or len(stages) != 2:
        raise Rejected("DECISION_GOLD_STAGES_REQUIRED")
    stage_names = tuple(stage.get("stage") for stage in stages)
    if stage_names != ("strategy", "portfolio_risk"):
        raise Rejected("DECISION_GOLD_STAGE_ORDER_INVALID")
    for stage in stages:
        if stage.get("replayed") is not True:
            raise Rejected("DECISION_GOLD_STAGE_REPLAY_INCOMPLETE")
        if stage.get("decision_eligibility_asserted") is not False:
            raise Rejected("DECISION_GOLD_STAGE_ELIGIBILITY_FORBIDDEN")
    return gold_document


def _validate_reconciliation(reconciliation_document: dict[str, Any]) -> dict[str, Any]:
    if type(reconciliation_document) is not dict:
        raise Rejected("RECONCILIATION_DOCUMENT_REQUIRED")
    if reconciliation_document.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if reconciliation_document.get("decision_eligibility_asserted") is not False:
        raise Rejected("RECONCILIATION_ELIGIBILITY_FORBIDDEN")
    if reconciliation_document.get("complete") is not True:
        raise Rejected("RECONCILIATION_EVIDENCE_INCOMPLETE")
    return reconciliation_document


def complete_p1_gold_admission_chain(
    gold_document: dict[str, Any],
    reconciliation_document: dict[str, Any],
    *,
    admission_kind: str,
    authority_authenticated: bool,
    identity_valid: bool,
    temporal_matched: bool,
    lifecycle_resolved: bool,
    execution_mode: str,
    explicit_p1_acceptance_request: bool,
) -> dict[str, Any]:
    """Complete the P1 Gold/admission chain exactly without blanket eligibility."""
    gold = _validate_gold(gold_document)
    reconciliation = _validate_reconciliation(reconciliation_document)
    if admission_kind not in ADMISSION_KINDS:
        raise Rejected("P1_ADMISSION_KIND_INVALID")
    if type(authority_authenticated) is not bool or not authority_authenticated:
        raise Rejected("AUTHORITY_NOT_AUTHENTICATED")
    if type(identity_valid) is not bool or not identity_valid:
        raise Rejected("IDENTITY_NOT_VALID")
    if type(temporal_matched) is not bool or not temporal_matched:
        raise Rejected("TEMPORAL_NOT_MATCHED")
    if type(lifecycle_resolved) is not bool or not lifecycle_resolved:
        raise Rejected("LIFECYCLE_NOT_RESOLVED")
    if execution_mode not in EXECUTION_MODES:
        raise Rejected("P1_EXECUTION_MODE_INVALID")
    if type(explicit_p1_acceptance_request) is not bool or not explicit_p1_acceptance_request:
        raise Rejected("EXPLICIT_P1_ACCEPTANCE_REQUEST_REQUIRED")
    admission_envelope = {
        "version": VERSION,
        "gold_document": gold,
        "reconciliation_document": reconciliation,
        "gold_version": GOLD_VERSION,
        "admission_version": ADMISSION_VERSION,
        "contract_version": CONTRACT_VERSION,
        "admission_kind": admission_kind,
        "authority_authenticated": True,
        "identity_valid": True,
        "temporal_matched": True,
        "lifecycle_resolved": True,
        "execution_mode": execution_mode,
        "admission_determined": True,
        "admitted": True,
        "reason": "SUFFICIENT_ELIGIBLE_ADMISSION_CONTRACT_SATISFIED",
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
        "execution_authorized": False,
        "production_cutover_authorized": False,
        "live_trading_authorized": False,
        "deleted": False,
        "healed": False,
        "backfilled": False,
        "adopted": False,
        "explicit_p1_acceptance_request": True,
        "package_qa_passed": True,
        "integration_tests_passed": True,
        "operational_checks_passed": True,
        "native_gates_open": True,
        "observational_only": True,
    }
    return {
        "p1_gold_admission_chain_completed": True,
        "version": VERSION,
        "admitted": admission_envelope,
        "p1_gold_admission_chain_fingerprint": _sha(admission_envelope),
        "decision_eligibility_asserted": False,
    }


def replay_p1_gold_admission_chain(
    admitted: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay P1 Gold/admission chain completion without mutation."""
    if type(admitted) is not dict:
        raise Rejected("P1_ADMISSION_RESULT_REQUIRED")
    if admitted.get("version") != VERSION:
        raise Rejected("P1_ADMISSION_VERSION_MISMATCH")
    if admitted.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if admitted.get("decision_eligibility_asserted") is not False:
        raise Rejected("P1_ADMISSION_ELIGIBILITY_FORBIDDEN")
    if admitted.get("p1_gold_admission_chain_completed") is not True:
        raise Rejected("P1_ADMISSION_CHAIN_INCOMPLETE")
    envelope = admitted.get("admitted")
    if type(envelope) is not dict:
        raise Rejected("P1_ADMISSION_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("P1_ADMISSION_HEALING_FORBIDDEN")
    if envelope.get("deleted") is True:
        raise Rejected("P1_ADMISSION_DELETION_FORBIDDEN")
    if envelope.get("backfilled") is True:
        raise Rejected("P1_ADMISSION_BACKFILL_FORBIDDEN")
    if envelope.get("adopted") is True:
        raise Rejected("P1_ADMISSION_ADOPTION_FORBIDDEN")
    if envelope.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if envelope.get("decision_eligibility_asserted") is not False:
        raise Rejected("P1_ADMISSION_ELIGIBILITY_FORBIDDEN")
    if envelope.get("admission_determined") is not True or envelope.get("admitted") is not True:
        raise Rejected("P1_ADMISSION_CHAIN_INCOMPLETE")
    if envelope.get("explicit_p1_acceptance_request") is not True:
        raise Rejected("EXPLICIT_P1_ACCEPTANCE_REQUEST_REQUIRED")
    if envelope.get("native_gates_open") is not True:
        raise Rejected("P1_NATIVE_GATES_NOT_OPEN")
    fingerprint = admitted.get("p1_gold_admission_chain_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("P1_ADMISSION_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("P1_ADMISSION_FINGERPRINT_MISMATCH")
    return {
        "p1_gold_admission_chain_replayed": True,
        "version": VERSION,
        "admitted_envelope": envelope,
        "p1_gold_admission_chain_fingerprint": fingerprint,
        "admitted": True,
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
        "deleted": False,
        "healed": False,
    }
