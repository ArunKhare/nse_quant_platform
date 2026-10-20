"""Proposal-only NIFTY iron-condor strategy.

The strategy emits a TradeProposal. It never submits, modifies, or cancels an
order.
"""

from __future__ import annotations

from typing import Any

from nse_quant.core.models import (
    ChainSnapshot,
    GateResult,
    Leg,
    MarketFeatures,
    OptionType,
    OrderSide,
    TradeProposal,
)
from nse_quant.core.settings import IronCondorProfileSettings, get_settings
from nse_quant.strategy.gates import GateEvaluator


class IronCondorMonitor:
    strategy_name = "iron_condor_monitor"

    def __init__(self, settings: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self.profile = self.settings.get_strategy_profile(self.strategy_name)
        if not isinstance(self.profile, IronCondorProfileSettings):
            raise TypeError(
                f"{self.strategy_name} must use IronCondorProfileSettings"
            )

        self.config = self.profile
        self.gates = GateEvaluator(self.settings)
        self.risk_settings = settings.get_effective_risk_settings(
            "iron_condor_monitor"
        )
        self.exit_settings = settings.get_effective_exit_settings("iron_condor_monitor")

    def evaluate(
        self,
        snapshot: ChainSnapshot,
        features: MarketFeatures,
        iv_history_count: int | None = None,
    ) -> tuple[TradeProposal | None, list[GateResult]]:
        if not snapshot.quotes:
            return None, []

        atm_strike = snapshot.atm_strike()
        wing = self.config.wing_distance_points

        short_call_strike = atm_strike + wing
        short_put_strike = atm_strike - wing
        long_call_strike = short_call_strike + wing
        long_put_strike = short_put_strike - wing

        required_strikes = [
            long_put_strike,
            short_put_strike,
            short_call_strike,
            long_call_strike,
        ]

        gates = self.gates.evaluate(snapshot, features, required_strikes, iv_history_count=iv_history_count)

        if not self.gates.all_passed(gates):
            return None, gates

        quote_lookup = {
            (quote.instrument.option_type.value, quote.instrument.strike): quote
            for quote in snapshot.quotes
        }

        legs = [
            self._leg(quote_lookup, OptionType.PE, long_put_strike, OrderSide.BUY),
            self._leg(quote_lookup, OptionType.PE, short_put_strike, OrderSide.SELL),
            self._leg(quote_lookup, OptionType.CE, short_call_strike, OrderSide.SELL),
            self._leg(quote_lookup, OptionType.CE, long_call_strike, OrderSide.BUY),
        ]

        if any(leg is None for leg in legs):
            gates.append(
                GateResult(
                    gate="required_legs_available",
                    passed=False,
                    reason="missing_required_quote",
                    details={"required_strikes": required_strikes},
                )
            )
            return None, gates

        valid_legs = [leg for leg in legs if leg is not None]
        credit = self._net_credit(valid_legs, quote_lookup)

        if credit < self.config.min_credit:
            gates.append(
                GateResult(
                    gate="minimum_credit",
                    passed=False,
                    reason=f"credit={credit:.2f}",
                    details={
                        "credit": credit,
                        "min_credit": self.config.min_credit,
                    },
                )
            )
            return None, gates

        proposal = TradeProposal(
            strategy=self.strategy_name,
            underlying=snapshot.underlying,
            expiry=snapshot.expiry,
            thesis=(
                "Range-bound NIFTY assumption supported by IV rank, IV-RV spread, "
                "and available expected-move estimate."
            ),
            legs=valid_legs,
            entry_limit_price=credit,
            target_price=credit * 0.5,
            stop_loss_price=credit * 2.0,
            expected_move_points=features.expected_move_points,
            metadata={
                "atm_strike": atm_strike,
                "long_put_strike": long_put_strike,
                "short_put_strike": short_put_strike,
                "short_call_strike": short_call_strike,
                "long_call_strike": long_call_strike,
                "net_credit": credit,
            },
        )

        gates.append(
            GateResult(
                gate="minimum_credit",
                passed=True,
                reason=f"credit={credit:.2f}",
                details={
                    "credit": credit,
                    "min_credit": self.config.min_credit,
                },
            )
        )

        return proposal, gates

    def _leg(
        self,
        quote_lookup: dict[tuple[str, float], Any],
        option_type: OptionType,
        strike: float,
        side: OrderSide,
    ) -> Leg | None:
        quote = quote_lookup.get((option_type.value, strike))

        if quote is None:
            return None

        return Leg(
            instrument=quote.instrument,
            side=side,
            lots=1,
        )

    @staticmethod
    def _net_credit(
        legs: list[Leg],
        quote_lookup: dict[tuple[str, float], Any],
    ) -> float:
        credit = 0.0

        for leg in legs:
            quote = quote_lookup.get(
                (
                    leg.instrument.option_type.value,
                    leg.instrument.strike,
                )
            )

            if quote is None:
                return 0.0

            price = quote.mid or quote.ltp

            if price is None:
                return 0.0

            signed_quantity = leg.quantity
            if leg.side == OrderSide.SELL:
                credit += price * signed_quantity
            else:
                credit -= price * signed_quantity

        return credit