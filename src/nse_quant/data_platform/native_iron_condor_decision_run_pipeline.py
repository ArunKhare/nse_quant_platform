"""End-to-end native iron-condor decision-run pipeline; observational only.

Evaluates and records a native strategy/portfolio-risk decision run, reconciles
it against current Silver-backed coverage, persists that reconciliation, and
exactly replays it. No eligibility, live trading, healing, backfill, adoption,
or execution authority. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.native_iron_condor_decision_reconciliation_persistence import (
    persist_native_iron_condor_decision_reconciliation,
)
from nse_quant.data_platform.native_iron_condor_decision_run_orchestrator import (
    NativeDecisionRunRequest,
    run_native_iron_condor_decision,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def run_and_reconcile_native_iron_condor_decision(
    decision_target: Any,
    reconciliation_target: Any,
    *,
    request: NativeDecisionRunRequest,
    coverage_report: dict[str, Any],
    expected_reconciliation_context_sha256: str,
) -> dict[str, Any]:
    """Run, record, reconcile, persist, and replay a native decision run."""
    if type(request) is not NativeDecisionRunRequest:
        raise Rejected("TYPED_NATIVE_DECISION_RUN_REQUEST_REQUIRED")
    if type(coverage_report) is not dict:
        raise Rejected("COVERAGE_REPORT_REQUIRED")
    if type(expected_reconciliation_context_sha256) is not str or len(expected_reconciliation_context_sha256) != 64:
        raise Rejected("EXACT_EXPECTED_CONTEXT_PIN_REQUIRED")

    run_result = run_native_iron_condor_decision(
        decision_target,
        request=request,
    )
    recording = run_result["recording"]
    revisions = {item["stage"]: item["revision_id"] for item in recording["stages"]}
    fingerprints = {item["stage"]: item["recording_fingerprint"] for item in recording["stages"]}
    stages = tuple(item["stage"] for item in recording["stages"])

    reconciliation_result = persist_native_iron_condor_decision_reconciliation(
        reconciliation_target,
        coverage_report=coverage_report,
        run_id=request.run_id,
        stages=stages,
        stage_revisions=revisions,
        stage_recording_fingerprints=fingerprints,
        expected_context_sha256=expected_reconciliation_context_sha256,
        actor_id=request.actor_id,
        code_revision=request.code_revision,
    )

    return {
        "run_id": request.run_id,
        "decision_run": run_result,
        "reconciliation": reconciliation_result,
        "decision_eligibility_asserted": False,
    }
