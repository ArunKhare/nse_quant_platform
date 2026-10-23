"""Conservative paper-margin estimation.

This is not a broker margin API. It provides a conservative, configurable
pre-trade estimate for defined-risk option structures.
"""

from __future__ import annotations

from dataclasses import dataclass

from nse_quant.core.models import OrderSide, TradeProposal


@dataclass(frozen=True)
class MarginEstimate:
    required_margin: float
    premium_outflow: float
    defined_risk: bool
    notes: list[str]


class MarginEstimator:
    def __init__(self, spot: float, premium_rate: float = 0.10) -> None:
        if spot <= 0:
            raise ValueError("spot must be positive")
        if premium_rate < 0:
            raise ValueError("premium_rate cannot be negative")

        self.spot = spot
        self.premium_rate = premium_rate

    def estimate(self, proposal: TradeProposal) -> MarginEstimate:
        premium_outflow = 0.0
        short_legs = 0
        long_legs = 0
        notes: list[str] = []

        for leg in proposal.legs:
            premium = leg.quantity * self._approximate_premium(leg.instrument.strike)
            if leg.side == OrderSide.BUY:
                premium_outflow += premium
                long_legs += 1
            else:
                short_legs += 1

        if short_legs == 0:
            notes.append("No short options; premium outflow only.")
        elif long_legs >= short_legs:
            notes.append("Defined-risk structure detected.")
        else:
            notes.append("More short than long legs; treat as undefined-risk.")

        required_margin = premium_outflow

        if short_legs > 0 and long_legs < short_legs:
            required_margin += self.spot * 0.10
            notes.append("Applied conservative naked-short margin buffer.")

        return MarginEstimate(
            required_margin=required_margin,
            premium_outflow=premium_outflow,
            defined_risk=short_legs == 0 or long_legs >= short_legs,
            notes=notes,
        )

    def _approximate_premium(self, strike: float) -> float:
        distance = abs(strike - self.spot)
        intrinsic = max(0.0, self.spot - strike)
        time_value = max(0.0, self.spot * self.premium_rate - distance * 0.05)
        return max(intrinsic, time_value, 0.5)
