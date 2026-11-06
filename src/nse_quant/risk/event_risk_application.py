"""Apply an event-risk decision to a trade proposal.

This is a conservative pre-trade adjustment. It never places orders and never
bypasses the kill switch, paper mode, or other risk controls.
"""

from __future__ import annotations

from nse_quant.core.models import TradeProposal
from nse_quant.risk.event_risk_policy import EventRiskDecision


def apply_event_risk_to_proposal(
    proposal: TradeProposal,
    decision: EventRiskDecision,
) -> TradeProposal | None:
    if decision.action == "BLOCK_NEW_ENTRIES":
        return None

    if decision.size_multiplier >= 1.0:
        return proposal

    reduced = proposal.model_copy(deep=True)
    for leg in reduced.legs:
        leg.lots = max(1, int(leg.lots * decision.size_multiplier))
    return reduced
