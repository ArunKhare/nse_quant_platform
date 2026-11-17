"""Native iron-condor decision-run orchestrator; observational only.

Evaluates native strategy and portfolio-risk stages, records their immutable
evidence-linked audited decision run, and exactly replays only stages that
actually ran. No eligibility, live trading, healing, backfill, adoption, or
execution authority. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nse_quant.data_platform.audited_decision_run_composite import (
    CompositeDecisionRunRequest,
    CompositeDecisionStage,
    composite_context,
    record_composite_audited_decision_run,
    replay_composite_audited_decision_run,
)
from nse_quant.data_platform.native_iron_condor_portfolio_risk_decision import (
    NativePortfolioRiskDecisionInputBundle,
    evaluate_native_portfolio_risk_decision,
    native_portfolio_risk_decision_fingerprint,
)
from nse_quant.data_platform.native_iron_condor_strategy_decision import (
    NativeStrategyDecisionInputBundle,
    evaluate_native_strategy_decision,
    native_strategy_decision_fingerprint,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


@dataclass(frozen=True)
class NativeDecisionRunRequest:
    run_id: str
    actor_id: str
    code_revision: str
    strategy_bundle: NativeStrategyDecisionInputBundle
    portfolio_risk_bundle: NativePortfolioRiskDecisionInputBundle


def _validate_request(request: NativeDecisionRunRequest) -> None:
    if type(request) is not NativeDecisionRunRequest:
        raise Rejected("TYPED_NATIVE_DECISION_RUN_REQUEST_REQUIRED")
    if type(request.run_id) is not str or not 1 <= len(request.run_id) <= 128:
        raise Rejected("EXACT_RUN_ID_REQUIRED")
    if type(request.actor_id) is not str or not request.actor_id:
        raise Rejected("EXACT_ACTOR_REQUIRED")
    if type(request.code_revision) is not str or not request.code_revision:
        raise Rejected("EXACT_CODE_REVISION_REQUIRED")
    if type(request.strategy_bundle) is not NativeStrategyDecisionInputBundle:
        raise Rejected("TYPED_NATIVE_STRATEGY_INPUT_BUNDLE_REQUIRED")
    if type(request.portfolio_risk_bundle) is not NativePortfolioRiskDecisionInputBundle:
        raise Rejected("TYPED_NATIVE_PORTFOLIO_RISK_INPUT_BUNDLE_REQUIRED")
    if (
        request.strategy_bundle.coverage_revision_id != request.portfolio_risk_bundle.coverage_revision_id
        or request.strategy_bundle.coverage_recording_fingerprint
        != request.portfolio_risk_bundle.coverage_recording_fingerprint
    ):
        raise Rejected("COVERAGE_IDENTITY_MISMATCH")


def run_native_iron_condor_decision(
    target: Any,
    *,
    request: NativeDecisionRunRequest,
) -> dict[str, Any]:
    """Evaluate, record, and exactly replay a native two-stage decision run."""
    _validate_request(request)

    strategy_outcome = evaluate_native_strategy_decision(request.strategy_bundle)
    strategy_inputs = {
        "coverage_revision_id": request.strategy_bundle.coverage_revision_id,
        "coverage_recording_fingerprint": request.strategy_bundle.coverage_recording_fingerprint,
        "evidence_refs": request.strategy_bundle.evidence_refs,
        "market_session": request.strategy_bundle.market_session,
        "iv_rank_and_history": request.strategy_bundle.iv_rank_and_history,
        "iv_rv_spread": request.strategy_bundle.iv_rv_spread,
        "expected_move": request.strategy_bundle.expected_move,
        "effective_proposal_configuration": request.strategy_bundle.effective_proposal_configuration,
        "chain_time_expiry_spot": request.strategy_bundle.chain_time_expiry_spot,
        "option_chain_and_contract_terms": request.strategy_bundle.option_chain_and_contract_terms,
        "candidate_liquidity": request.strategy_bundle.candidate_liquidity,
    }
    strategy_fingerprint = native_strategy_decision_fingerprint(
        inputs=strategy_inputs,
        outcome=strategy_outcome,
    )

    portfolio_risk_bundle = NativePortfolioRiskDecisionInputBundle(
        coverage_revision_id=request.portfolio_risk_bundle.coverage_revision_id,
        coverage_recording_fingerprint=request.portfolio_risk_bundle.coverage_recording_fingerprint,
        evidence_refs=request.portfolio_risk_bundle.evidence_refs,
        strategy_outcome=strategy_outcome,
        proposal=request.portfolio_risk_bundle.proposal,
        open_positions=request.portfolio_risk_bundle.open_positions,
        settings=request.portfolio_risk_bundle.settings,
    )
    portfolio_risk_outcome = evaluate_native_portfolio_risk_decision(portfolio_risk_bundle)
    portfolio_risk_inputs = {
        "coverage_revision_id": portfolio_risk_bundle.coverage_revision_id,
        "coverage_recording_fingerprint": portfolio_risk_bundle.coverage_recording_fingerprint,
        "evidence_refs": portfolio_risk_bundle.evidence_refs,
        "strategy_outcome": strategy_outcome,
        "proposal": portfolio_risk_bundle.proposal,
        "open_positions": portfolio_risk_bundle.open_positions,
        "settings": {
            "max_open_positions": portfolio_risk_bundle.settings.max_open_positions,
            "max_notional_exposure": portfolio_risk_bundle.settings.max_notional_exposure,
            "max_concentration_pct": portfolio_risk_bundle.settings.max_concentration_pct,
        },
    }
    portfolio_risk_fingerprint = native_portfolio_risk_decision_fingerprint(
        inputs=portfolio_risk_inputs,
        outcome=portfolio_risk_outcome,
    )

    composite_request = CompositeDecisionRunRequest(
        run_id=request.run_id,
        coverage_revision_id=request.strategy_bundle.coverage_revision_id,
        coverage_recording_fingerprint=request.strategy_bundle.coverage_recording_fingerprint,
        stages=(
            CompositeDecisionStage(
                stage="strategy",
                decision_fingerprint=strategy_fingerprint,
                inputs=strategy_inputs,
                outcome=strategy_outcome,
                evidence_refs=request.strategy_bundle.evidence_refs,
            ),
            CompositeDecisionStage(
                stage="portfolio_risk",
                decision_fingerprint=portfolio_risk_fingerprint,
                inputs=portfolio_risk_inputs,
                outcome=portfolio_risk_outcome,
                evidence_refs=request.portfolio_risk_bundle.evidence_refs,
            ),
        ),
    )

    recording = record_composite_audited_decision_run(
        target,
        request=composite_request,
        expected_context_sha256=composite_context(composite_request),
        actor_id=request.actor_id,
        code_revision=request.code_revision,
    )

    revisions = {item["stage"]: item["revision_id"] for item in recording["stages"]}
    fingerprints = {item["stage"]: item["recording_fingerprint"] for item in recording["stages"]}
    replay = replay_composite_audited_decision_run(
        target,
        run_id=request.run_id,
        stages=("strategy", "portfolio_risk"),
        expected_stage_revisions=revisions,
        expected_stage_recording_fingerprints=fingerprints,
    )

    return {
        "run_id": request.run_id,
        "strategy_outcome": strategy_outcome,
        "portfolio_risk_outcome": portfolio_risk_outcome,
        "recording": recording,
        "replay": replay,
        "decision_eligibility_asserted": False,
    }
