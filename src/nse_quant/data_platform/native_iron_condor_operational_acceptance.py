"""Integrated operational acceptance harness for native iron-condor decisions.

Runs a bounded, multi-day acceptance plan across complete trading days: native
decision-run recording, coverage evidence-link validation, authoritative
identity/time validation, reconciliation persistence, evidence-completeness
validation, admission evaluation, and exact replay. Returns an observational
acceptance result only. No eligibility, live trading, healing, backfill,
adoption, or execution authority. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.native_iron_condor_decision_admission import (
    evaluate_native_iron_condor_decision_admission,
)
from nse_quant.data_platform.native_iron_condor_decision_loop_evidence_integration import (
    run_native_iron_condor_decision_loop_with_evidence,
)
from nse_quant.data_platform.native_iron_condor_decision_run_orchestrator import (
    NativeDecisionRunRequest,
)
from nse_quant.data_platform.native_iron_condor_reconciliation_evidence_completeness import (
    validate_reconciliation_evidence_completeness,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-iron-condor-operational-acceptance@1"
COMMAND = "run.native_iron_condor_operational_acceptance@1"
MAX_DAYS = 30


def _validate_plan(plan: dict[str, Any]) -> None:
    if type(plan) is not dict:
        raise Rejected("ACCEPTANCE_PLAN_REQUIRED")
    if plan.get("version") != VERSION:
        raise Rejected("ACCEPTANCE_PLAN_VERSION_MISMATCH")
    days = plan.get("trading_days")
    if type(days) is not list or not 1 <= len(days) <= MAX_DAYS:
        raise Rejected("ACCEPTANCE_TRADING_DAYS_INVALID")
    for day in days:
        if type(day) is not dict or not day.get("trading_date"):
            raise Rejected("ACCEPTANCE_TRADING_DAY_INVALID")


def run_native_iron_condor_operational_acceptance(
    decision_target: Any,
    reconciliation_target: Any,
    acceptance_target: Any,
    *,
    plan: dict[str, Any],
    requests: list[NativeDecisionRunRequest],
    coverage_reports: list[dict[str, Any]],
    authoritative_boundaries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run a bounded multi-day operational acceptance plan."""
    _validate_plan(plan)
    if type(requests) is not list or not requests:
        raise Rejected("ACCEPTANCE_REQUESTS_REQUIRED")
    if type(coverage_reports) is not list or not coverage_reports:
        raise Rejected("ACCEPTANCE_COVERAGE_REPORTS_REQUIRED")
    if type(authoritative_boundaries) is not list or not authoritative_boundaries:
        raise Rejected("ACCEPTANCE_BOUNDARIES_REQUIRED")
    if not (len(requests) == len(coverage_reports) == len(authoritative_boundaries) == len(plan["trading_days"])):
        raise Rejected("ACCEPTANCE_PLAN_LENGTH_MISMATCH")

    day_results: list[dict[str, Any]] = []
    for index, day in enumerate(plan["trading_days"]):
        request = requests[index]
        coverage = coverage_reports[index]
        boundary = authoritative_boundaries[index]
        if request.run_id != boundary.get("run_id"):
            raise Rejected("ACCEPTANCE_RUN_BOUNDARY_MISMATCH")
        loop_result = run_native_iron_condor_decision_loop_with_evidence(
            decision_target,
            reconciliation_target,
            request=request,
            coverage_report=coverage,
            authoritative_boundary=boundary,
        )
        completeness = validate_reconciliation_evidence_completeness(loop_result["replay"]["reconciliation"])
        if completeness["complete_evidence"] is not True:
            raise Rejected("ACCEPTANCE_EVIDENCE_INCOMPLETE")
        admission = evaluate_native_iron_condor_decision_admission(
            loop_result["reconciliation"]["reconciliation"],
            loop_result["replay"]["reconciliation"],
        )
        if admission["admission_determined"] is not True:
            raise Rejected("ACCEPTANCE_ADMISSION_NOT_DETERMINED")
        day_results.append(
            {
                "trading_date": day["trading_date"],
                "run_id": request.run_id,
                "reconciliation_revision_id": loop_result["reconciliation"]["revision_id"],
                "reconciliation_recording_fingerprint": loop_result["reconciliation"]["recording_fingerprint"],
                "evidence_complete": True,
                "admission_determined": True,
                "admitted": admission["admitted"],
                "decision_eligibility_asserted": False,
                "execution_authorized": False,
            }
        )
    return {
        "acceptance_determined": True,
        "accepted": False,
        "reason": "OPERATIONAL_ACCEPTANCE_EVIDENCE_COMPLETE",
        "version": VERSION,
        "trading_day_count": len(day_results),
        "day_results": day_results,
        "decision_eligibility_asserted": False,
        "execution_authorized": False,
    }
