"""Exact replay of the full decision loop.

Combines full stage-chain replay, audited decision record, and strategy
evaluation integration into a single replayable record, without granting
eligibility or enabling live trading. Addresses the "exact replay of the full
decision loop" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from nse_quant.data_platform.audited_decision_record import (
    DecisionRecord,
    audit_decision,
)
from nse_quant.data_platform.full_stage_chain_replay import (
    FullStageRecord,
    replay_full_stage_chain,
)
from nse_quant.data_platform.strategy_evaluation_integration import (
    AnalyticsOutcome,
    GateOutputs,
    PortfolioRiskOutcome,
    integrate_strategy_evaluation,
)


class FullLoopRequest(BaseModel):
    gates: GateOutputs
    analytics: AnalyticsOutcome
    portfolio_risk: PortfolioRiskOutcome
    evaluators: dict[str, Any] = Field(default_factory=dict)


class FullLoopReplayRecord(BaseModel):
    integrated: Any
    audited: Any
    replayed: list[Any] = Field(default_factory=list)
    replayable: bool
    reason: str
    decision_eligibility_asserted: bool = False


def replay_full_decision_loop(
    *,
    request: FullLoopRequest,
) -> FullLoopReplayRecord:
    """Replay the full decision loop end-to-end into a single replayable record."""
    if type(request) is not FullLoopRequest:
        return FullLoopReplayRecord(
            integrated=None,
            audited=None,
            replayed=[],
            replayable=False,
            reason="INVALID_REQUEST",
        )

    integrated = integrate_strategy_evaluation(
        gates=request.gates,
        analytics=request.analytics,
        portfolio_risk=request.portfolio_risk,
    )

    if (
        type(request.gates) is not GateOutputs
        or type(request.analytics) is not AnalyticsOutcome
        or type(request.portfolio_risk) is not PortfolioRiskOutcome
    ):
        return FullLoopReplayRecord(
            integrated=integrated,
            audited=None,
            replayed=[],
            replayable=False,
            reason="FULL_LOOP_NOT_REPLAYABLE",
        )

    stage_inputs = dict(
        gates=request.gates.model_dump(),
        analytics=request.analytics.model_dump(),
        portfolio_risk=request.portfolio_risk.model_dump(),
    )
    strategy_outcome = integrated.model_dump()
    audited = audit_decision(
        record=DecisionRecord(
            stage="strategy",
            inputs=stage_inputs,
            outcome=strategy_outcome,
        )
    )

    replayed = replay_full_stage_chain(
        records=[
            FullStageRecord(
                stage=stage,
                inputs=stage_inputs,
                outcome=(strategy_outcome if stage == "strategy" else stage_inputs),
            )
            for stage in (
                "kill_switch",
                "safety_boundary",
                "publication_admission",
                "native_inputs",
                "strategy",
                "portfolio_risk",
                "execution",
            )
        ],
        evaluators=request.evaluators,
    )

    replayable = audited.recorded and all(r.outcome_matches for r in replayed)
    return FullLoopReplayRecord(
        integrated=integrated,
        audited=audited,
        replayed=replayed,
        replayable=replayable,
        reason="FULL_LOOP_REPLAYABLE" if replayable else "FULL_LOOP_NOT_REPLAYABLE",
        decision_eligibility_asserted=False,
    )
