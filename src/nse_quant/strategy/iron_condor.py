"""Proposal-only NIFTY iron-condor strategy.


The strategy emits a TradeProposal. It never submits, modifies, or cancels an
order.
"""

from __future__ import annotations

from datetime import UTC
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
from nse_quant.core.settings import (
    IronCondorProfileSettings,
    RiskSettings,
    get_settings,
)
from nse_quant.strategy.gates import GateEvaluator


class IronCondorMonitor:
    """Evaluate market conditions and produce iron-condor proposals."""

    # This strategy exposes evaluate() as its single public operation.
    # pylint: disable=too-few-public-methods
    strategy_name = "iron_condor_monitor"

    def __init__(self, settings: Any | None = None) -> None:
        self.settings = settings or get_settings()

        self.profile = self.settings.get_strategy_profile(self.strategy_name)
        if not isinstance(self.profile, IronCondorProfileSettings):
            raise TypeError(f"{self.strategy_name} must use IronCondorProfileSettings")

        self.config = self.profile
        self.risk_settings: RiskSettings = self.settings.get_effective_risk_settings(
            self.strategy_name
        )
        self.exit_settings = self.settings.get_effective_exit_settings(self.strategy_name)
        self.gates = GateEvaluator(
            self.settings,
            risk_limits=self.risk_settings,
        )

    def evaluate(
        self,
        snapshot: ChainSnapshot,
        features: MarketFeatures,
        iv_history_count: int | None = None,
    ) -> tuple[TradeProposal | None, list[GateResult]]:
        if not snapshot.quotes:
            return None, []

        snapshot_date = snapshot.ts.astimezone(UTC).date()

        if snapshot_date >= snapshot.expiry:
            return None, [
                GateResult(
                    gate="expiry_available",
                    passed=False,
                    reason="same_day_expiry",
                    details={
                        "snapshot_date": snapshot_date.isoformat(),
                        "expiry": snapshot.expiry.isoformat(),
                    },
                )
            ]

        atm_strike = snapshot.atm_strike()
        wing = self.config.wing_distance_points

        short_put_strike = atm_strike - wing
        short_call_strike = atm_strike + wing

        quote_lookup = {
            (quote.instrument.option_type.value, quote.instrument.strike): quote
            for quote in snapshot.quotes
        }

        long_put_quote = self._select_long_quote(
            quote_lookup=quote_lookup,
            option_type=OptionType.PE,
            target_strike=short_put_strike - wing,
            direction=-1,
            max_spread_pct=self.risk_settings.max_spread_pct,
        )

        long_call_quote = self._select_long_quote(
            quote_lookup=quote_lookup,
            option_type=OptionType.CE,
            target_strike=short_call_strike + wing,
            direction=1,
            max_spread_pct=self.risk_settings.max_spread_pct,
        )

        if long_put_quote is None or long_call_quote is None:
            gates = self.gates.evaluate(
                snapshot,
                features,
                [
                    short_put_strike - wing,
                    short_put_strike,
                    short_call_strike,
                    short_call_strike + wing,
                ],
                iv_history_count=iv_history_count,
            )

            gates.append(
                GateResult(
                    gate="long_wing_liquidity",
                    passed=False,
                    reason="no_liquid_long_wing",
                    details={
                        "long_put_target": short_put_strike - wing,
                        "long_call_target": short_call_strike + wing,
                        "max_spread_pct": self.risk_settings.max_spread_pct,
                    },
                )
            )
            return None, gates

        long_put_strike = long_put_quote.instrument.strike
        long_call_strike = long_call_quote.instrument.strike

        required_strikes = [
            long_put_strike,
            short_put_strike,
            short_call_strike,
            long_call_strike,
        ]

        gates = self.gates.evaluate(
            snapshot,
            features,
            required_strikes,
            iv_history_count=iv_history_count,
        )

        if not self.gates.all_passed(gates):
            return None, gates

        legs = [
            self._leg(
                quote_lookup,
                OptionType.PE,
                long_put_strike,
                OrderSide.BUY,
            ),
            self._leg(
                quote_lookup,
                OptionType.PE,
                short_put_strike,
                OrderSide.SELL,
            ),
            self._leg(
                quote_lookup,
                OptionType.CE,
                short_call_strike,
                OrderSide.SELL,
            ),
            self._leg(
                quote_lookup,
                OptionType.CE,
                long_call_strike,
                OrderSide.BUY,
            ),
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
        credit = self._net_credit(valid_legs)

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

        entry_price = quote.mid or quote.ltp
        if entry_price is None or entry_price <= 0:
            return None

        return Leg(
            instrument=quote.instrument,
            side=side,
            lots=1,
            entry_price=entry_price,
        )

    @staticmethod
    def _net_credit(
        legs: list[Leg],
    ) -> float:
        credit = 0.0

        for leg in legs:
            if leg.entry_price is None:
                return 0.0

            if leg.side == OrderSide.SELL:
                credit += leg.entry_price * leg.quantity
            else:
                credit -= leg.entry_price * leg.quantity

        return credit

    def _select_long_quote(
        self,
        quote_lookup: dict[tuple[str, float], Any],
        option_type: OptionType,
        target_strike: float,
        direction: int,
        max_spread_pct: float,
    ) -> Any | None:
        strikes = sorted(
            strike for contract_type, strike in quote_lookup if contract_type == option_type.value
        )

        if direction < 0:
            candidates = [strike for strike in strikes if strike <= target_strike]
            candidates.reverse()
        else:
            candidates = [strike for strike in strikes if strike >= target_strike]

        for strike in candidates:
            quote = quote_lookup.get((option_type.value, strike))

            if quote is None:
                continue

            spread = quote.spread_pct

            # Quotes without bid/ask have no measurable spread. Treat them as
            # eligible here; the liquidity gate records missing bid/ask as a
            # warning rather than rejecting the leg.
            if spread is None or spread <= max_spread_pct:
                return quote

        return None
