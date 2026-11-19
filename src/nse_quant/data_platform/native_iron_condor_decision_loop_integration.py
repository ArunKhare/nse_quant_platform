"""Read-only decision-loop integration for native iron-condor decisions.

Runs the native strategy/portfolio-risk decision pipeline, reconciles it against
current Silver-backed coverage with the authoritative identity/time boundary,
persists that reconciliation, and exactly replays it. Returns an observational
result only. No eligibility, live trading, healing, backfill, adoption, or
execution authority. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.audited_decision_reconciliation_silver import (
    reconciliation_context,
)
from nse_quant.data_platform.native_iron_condor_decision_reconciliation_boundary import (
    build_reconciliation_with_authoritative_boundary,
    record_reconciliation_with_authoritative_boundary,
    replay_reconciliation_with_authoritative_boundary,
)
from nse_quant.data_platform.native_iron_condor_decision_run_orchestrator import (
    NativeDecisionRunRequest,
    run_native_iron_condor_decision,
)
from nse_quant.data_platform.native_strategy_coverage_evidence_links import (
    coverage_evidence_links_context,
    validate_coverage_evidence_links,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected
from nse_quant.data_platform.native_strategy_requirements import (
    STRATEGY,
)

VERSION = "native-iron-condor-decision-loop-integration@1"
COMMAND = "run.native_iron_condor_decision_loop@1"


def run_native_iron_condor_decision_loop(
    decision_target: Any,
    reconciliation_target: Any,
    *,
    request: NativeDecisionRunRequest,
    coverage_report: dict[str, Any],
    authoritative_boundary: dict[str, Any],
) -> dict[str, Any]:
    """Run, reconcile with boundary evidence, persist, and replay a decision run."""
    if type(request) is not NativeDecisionRunRequest:
        raise Rejected("TYPED_NATIVE_DECISION_RUN_REQUEST_REQUIRED")
    if type(coverage_report) is not dict:
        raise Rejected("COVERAGE_REPORT_REQUIRED")
    if type(authoritative_boundary) is not dict:
        raise Rejected("AUTHORITATIVE_BOUNDARY_DOCUMENT_REQUIRED")

    run_result = run_native_iron_condor_decision(
        decision_target,
        request=request,
    )
    recording = run_result["recording"]
    revisions = {item["stage"]: item["revision_id"] for item in recording["stages"]}
    fingerprints = {item["stage"]: item["recording_fingerprint"] for item in recording["stages"]}
    stages = tuple(item["stage"] for item in recording["stages"])

    reconciliation = {
        "version": "native-audited-decision-reconciliation-silver-recording@1",
        "strategy": STRATEGY,
        "run_id": request.run_id,
        "coverage_revision_id": coverage_report["revision_id"],
        "coverage_recording_fingerprint": coverage_report["recording_fingerprint"],
        "coverage": coverage_report,
        "stages": [
            {
                "stage": stage,
                "replayed": True,
                "revision_id": revisions[stage],
                "recording_fingerprint": fingerprints[stage],
                "decision_eligibility_asserted": False,
            }
            for stage in stages
        ],
        "complete": False,
        "decision_eligibility_asserted": False,
    }
    validate_coverage_evidence_links(coverage_report)
    reconciliation["coverage_evidence_links_context"] = coverage_evidence_links_context(coverage_report)
    extended = build_reconciliation_with_authoritative_boundary(
        reconciliation,
        authoritative_boundary,
    )
    context = reconciliation_context(extended)
    recorded = record_reconciliation_with_authoritative_boundary(
        reconciliation_target,
        reconciliation=reconciliation,
        boundary=authoritative_boundary,
        expected_context_sha256=context,
        actor_id=request.actor_id,
        code_revision=request.code_revision,
    )
    replayed = replay_reconciliation_with_authoritative_boundary(
        reconciliation_target,
        run_id=request.run_id,
        expected_revision_id=recorded["revision_id"],
        expected_recording_fingerprint=recorded["recording_fingerprint"],
    )
    return {
        "run_id": request.run_id,
        "decision_run": run_result,
        "reconciliation": recorded,
        "replay": replayed,
        "decision_eligibility_asserted": False,
    }
