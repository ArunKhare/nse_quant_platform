"""Evidence-completeness validation for persisted native reconciliations.

Validates that a persisted reconciliation carries authoritative identity/time
evidence, coverage evidence-link context, and exact replay coverage for every
recorded stage. This is observational validation only: no eligibility, live
trading, healing, backfill, adoption, or execution authority.
POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-iron-condor-reconciliation-evidence-completeness@1"
COMMAND = "validate.native_iron_condor_reconciliation_evidence_completeness@1"


def validate_reconciliation_evidence_completeness(
    reconciliation: dict[str, Any],
) -> dict[str, Any]:
    """Validate evidence completeness for a persisted reconciliation."""
    if type(reconciliation) is not dict:
        raise Rejected("RECONCILIATION_DOCUMENT_REQUIRED")
    if reconciliation.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if reconciliation.get("decision_eligibility_asserted") is not False:
        raise Rejected("RECONCILIATION_ELIGIBILITY_FORBIDDEN")
    if reconciliation.get("complete") is True:
        raise Rejected("RECONCILIATION_COMPLETION_NOT_ASSERTABLE")

    boundary = reconciliation.get("authoritative_boundary")
    if type(boundary) is not dict:
        raise Rejected("AUTHORITATIVE_BOUNDARY_CONTEXT_MISSING")
    if not reconciliation.get("authoritative_boundary_context"):
        raise Rejected("AUTHORITATIVE_BOUNDARY_CONTEXT_MISSING")

    evidence_context = reconciliation.get("coverage_evidence_links_context")
    if type(evidence_context) is not str or not evidence_context:
        raise Rejected("COVERAGE_EVIDENCE_LINKS_CONTEXT_MISSING")

    stages = reconciliation.get("stages")
    if type(stages) is not list or not stages:
        raise Rejected("RECONCILIATION_STAGES_REQUIRED")
    for stage in stages:
        if type(stage) is not dict:
            raise Rejected("RECONCILIATION_STAGE_DOCUMENT_REQUIRED")
        if stage.get("replayed") is not True:
            raise Rejected("RECONCILIATION_STAGE_REPLAY_INCOMPLETE")
        if stage.get("decision_eligibility_asserted") is not False:
            raise Rejected("RECONCILIATION_STAGE_ELIGIBILITY_FORBIDDEN")

    return {
        "complete_evidence": True,
        "version": VERSION,
        "stage_count": len(stages),
        "authoritative_boundary_present": True,
        "coverage_evidence_links_present": True,
        "decision_eligibility_asserted": False,
    }
