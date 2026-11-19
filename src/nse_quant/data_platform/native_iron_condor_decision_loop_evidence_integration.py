"""Decision-loop integration with authoritative boundary and evidence links.

Runs the native strategy/portfolio-risk decision pipeline, validates coverage
evidence links and the authoritative identity/time boundary, embeds both exact
contexts in a reconciliation, persists it, and exactly replays it. Returns an
observational result only. No eligibility, live trading, healing, backfill,
adoption, or execution authority. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.audited_decision_reconciliation_silver import (
    VERSION as BASE_RECONCILIATION_VERSION,
)
from nse_quant.data_platform.audited_decision_reconciliation_silver import (
    reconciliation_context,
    record_audited_decision_reconciliation,
)
from nse_quant.data_platform.native_iron_condor_decision_reconciliation_boundary import (
    build_reconciliation_with_authoritative_boundary,
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
from nse_quant.data_platform.native_strategy_requirements import STRATEGY

VERSION = "native-iron-condor-decision-loop-evidence-integration@1"
COMMAND = "run.native_iron_condor_decision_loop_evidence@1"


def run_native_iron_condor_decision_loop_with_evidence(
    decision_target: Any,
    reconciliation_target: Any,
    *,
    request: NativeDecisionRunRequest,
    coverage_report: dict[str, Any],
    authoritative_boundary: dict[str, Any],
) -> dict[str, Any]:
    """Run, reconcile with boundary and evidence links, persist, and replay."""
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

    validate_coverage_evidence_links(coverage_report)
    reconciliation = {
        "version": BASE_RECONCILIATION_VERSION,
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
    extended = build_reconciliation_with_authoritative_boundary(
        reconciliation,
        authoritative_boundary,
    )
    extended["coverage_evidence_links_context"] = coverage_evidence_links_context(coverage_report)
    context = reconciliation_context(extended)
    recorded = record_audited_decision_reconciliation(
        reconciliation_target,
        reconciliation=extended,
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
        "coverage_evidence_links_context": extended["coverage_evidence_links_context"],
        "decision_eligibility_asserted": False,
    }
