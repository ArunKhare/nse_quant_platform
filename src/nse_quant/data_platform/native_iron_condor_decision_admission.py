"""Eligible publication/admission contract for native iron-condor decisions.

Evaluates a versioned Gold decision publication candidate against required
evidence completeness and returns an admission determination. This contract
does not grant blanket eligibility, authorize live trading, healing, backfill,
adoption, or execution. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.native_iron_condor_reconciliation_evidence_completeness import (
    validate_reconciliation_evidence_completeness,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected
from nse_quant.data_platform.native_strategy_requirements import (
    STRATEGY,
)

VERSION = "native-iron-condor-decision-admission@1"
COMMAND = "evaluate.native_iron_condor_decision_admission@1"


def _pin(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def evaluate_native_iron_condor_decision_admission(
    gold_document: dict[str, Any],
    reconciliation_document: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate admission eligibility for a Gold decision candidate."""
    if type(gold_document) is not dict:
        raise Rejected("DECISION_GOLD_DOCUMENT_REQUIRED")
    if type(reconciliation_document) is not dict:
        raise Rejected("RECONCILIATION_DOCUMENT_REQUIRED")
    if gold_document.get("version") != "native-iron-condor-decision-gold@1":
        raise Rejected("DECISION_GOLD_VERSION_MISMATCH")
    if gold_document.get("strategy") != STRATEGY:
        raise Rejected("DECISION_GOLD_STRATEGY_MISMATCH")
    if gold_document.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if gold_document.get("decision_eligibility_asserted") is not False:
        raise Rejected("DECISION_GOLD_ELIGIBILITY_FORBIDDEN")
    if reconciliation_document.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if reconciliation_document.get("decision_eligibility_asserted") is not False:
        raise Rejected("RECONCILIATION_ELIGIBILITY_FORBIDDEN")

    completeness = validate_reconciliation_evidence_completeness(reconciliation_document)
    if completeness["complete_evidence"] is not True:
        raise Rejected("RECONCILIATION_EVIDENCE_INCOMPLETE")

    reconciliation_revision = gold_document.get("reconciliation_revision_id")
    reconciliation_fingerprint = gold_document.get("reconciliation_recording_fingerprint")
    if not _pin(reconciliation_revision) or not _pin(reconciliation_fingerprint):
        raise Rejected("DECISION_GOLD_RECONCILIATION_EVIDENCE_INVALID")

    identity_revision = gold_document.get("identity_time_evidence_revision_id")
    identity_fingerprint = gold_document.get("identity_time_evidence_recording_fingerprint")
    if not _pin(identity_revision) or not _pin(identity_fingerprint):
        raise Rejected("DECISION_GOLD_IDENTITY_TIME_EVIDENCE_INVALID")

    availability_revision = gold_document.get("availability_economic_evidence_revision_id")
    availability_fingerprint = gold_document.get("availability_economic_evidence_recording_fingerprint")
    if not _pin(availability_revision) or not _pin(availability_fingerprint):
        raise Rejected("DECISION_GOLD_AVAILABILITY_ECONOMIC_EVIDENCE_INVALID")

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

    return {
        "admission_determined": True,
        "admitted": False,
        "reason": "EVIDENCE_COMPLETE_ADMISSION_CONTRACT_PENDING",
        "version": VERSION,
        "strategy": STRATEGY,
        "run_id": gold_document["run_id"],
        "reconciliation_revision_id": reconciliation_revision,
        "identity_time_evidence_revision_id": identity_revision,
        "availability_economic_evidence_revision_id": availability_revision,
        "decision_eligibility_asserted": False,
        "execution_authorized": False,
    }
