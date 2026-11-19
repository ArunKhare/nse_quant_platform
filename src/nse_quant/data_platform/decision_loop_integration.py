"""Decision-loop integration.

Combines strategy evaluation, audited decision record, and stage replay into a
full decision-loop record, without granting eligibility or enabling live trading.
Addresses the "decision-loop integration" sub-gap of gate 6 from
docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from nse_quant.data_platform.audited_decision_record import (
    DecisionRecord,
    audit_decision,
)
from nse_quant.data_platform.stage_replay import (
    StageRecord,
    replay_stage_chain,
)
from nse_quant.data_platform.strategy_evaluation_integration import (
    AnalyticsOutcome,
    GateOutputs,
    PortfolioRiskOutcome,
    integrate_strategy_evaluation,
)


class DecisionLoopRequest(BaseModel):
    gates: GateOutputs
    analytics: AnalyticsOutcome
    portfolio_risk: PortfolioRiskOutcome
    evaluators: dict[str, Any] = Field(default_factory=dict)


class DecisionLoopRecord(BaseModel):
    integrated: Any
    audited: Any
    replayed: list[Any] = Field(default_factory=list)
    complete: bool
    reason: str
    decision_eligibility_asserted: bool = False


def run_decision_loop(
    *,
    request: DecisionLoopRequest,
) -> DecisionLoopRecord:
    """Run the full decision loop: integrate, audit, replay."""
    if type(request) is not DecisionLoopRequest:
        return DecisionLoopRecord(
            integrated=None,
            audited=None,
            replayed=[],
            complete=False,
            reason="INVALID_REQUEST",
        )

    integrated = integrate_strategy_evaluation(
        gates=request.gates,
        analytics=request.analytics,
        portfolio_risk=request.portfolio_risk,
    )

    stage_inputs = dict(
        gates=request.gates.model_dump(),
        analytics=request.analytics.model_dump(),
        portfolio_risk=request.portfolio_risk.model_dump(),
    )
    audited = audit_decision(
        record=DecisionRecord(
            stage="strategy",
            inputs=stage_inputs,
            outcome=integrated.model_dump(),
        )
    )

    replayed = replay_stage_chain(
        records=[
            StageRecord(
                stage="strategy",
                inputs=stage_inputs,
                outcome=integrated.model_dump(),
            ),
        ],
        evaluators=request.evaluators,
    )

    complete = integrated.approved and audited.recorded and all(r.outcome_matches for r in replayed)
    return DecisionLoopRecord(
        integrated=integrated,
        audited=audited,
        replayed=replayed,
        complete=complete,
        reason="DECISION_LOOP_COMPLETE" if complete else "DECISION_LOOP_INCOMPLETE",
        decision_eligibility_asserted=False,
    )
