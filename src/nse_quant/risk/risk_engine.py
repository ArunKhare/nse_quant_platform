"""Independent pre-trade risk controls.

The risk engine never generates strategy ideas and never places orders.
It evaluates TradeProposal objects against persisted portfolio state and
configuration-driven limits.
"""

from __future__ import annotations

from typing import Any

from nse_quant.core.models import (
    GateResult,
    MarketFeatures,
    OptionQuote,
    RiskDecision,
    TradeProposal,
)
from nse_quant.core.settings import get_settings
from nse_quant.persistence.repositories import PositionRepository


class RiskEngine:
    def __init__(
        self,
        conn: Any,
        settings: Any | None = None,
        position_repository: PositionRepository | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.limits = self.settings.risk
        self.positions = position_repository or PositionRepository(conn)

    def evaluate(
        self,
        proposal: TradeProposal,
        features: MarketFeatures,
        quote_lookup: dict[tuple[str, float], OptionQuote] | None = None,
    ) -> RiskDecision:
        checks: list[GateResult] = []
        reasons: list[str] = []

        self._check_allowed_strategy(proposal, checks, reasons)
        self._check_lot_limit(proposal, checks, reasons)
        self._check_open_positions(checks, reasons)
        self._check_daily_loss(checks, reasons)
        self._check_notional(proposal, features, checks, reasons)
        self._check_defined_risk(proposal, checks, reasons)
        self._check_leg_liquidity(proposal, quote_lookup, checks, reasons)

        return RiskDecision(
            approved=not reasons,
            reasons=reasons,
            checks=checks,
        )

    def apply_regime_limits(
        self,
        proposal: TradeProposal,
        features: MarketFeatures,
        regime_limits: Any,
    ) -> RiskDecision:
        """Apply point-in-time, regime-specific pre-trade limits."""
        checks: list[GateResult] = []
        reasons: list[str] = []

        if not regime_limits.allowed:
            checks.append(
                GateResult(
                    gate="regime_risk_limits",
                    passed=False,
                    reason=regime_limits.reason,
                    details={
                        "regime": regime_limits.regime,
                    },
                )
            )
            reasons.append(regime_limits.reason)

            return RiskDecision(
                approved=False,
                reasons=reasons,
                checks=checks,
            )

        max_lots = max(
            (leg.lots for leg in proposal.legs),
            default=0,
        )
        lots_ok = (
            0 < max_lots <= regime_limits.max_lots_per_order
        )

        checks.append(
            GateResult(
                gate="regime_max_lots_per_order",
                passed=lots_ok,
                reason=f"max_leg_lots={max_lots}",
                details={
                    "max_lots": max_lots,
                    "limit": regime_limits.max_lots_per_order,
                },
            )
        )

        if not lots_ok:
            reasons.append("regime_max_lots_exceeded")

        notional = sum(
            abs(leg.quantity) * features.spot / 10
            for leg in proposal.legs
        )
        notional_ok = (
            notional <= regime_limits.max_notional_exposure
        )

        checks.append(
            GateResult(
                gate="regime_max_notional_exposure",
                passed=notional_ok,
                reason=f"notional={notional:.2f}",
                details={
                    "notional": notional,
                    "limit": regime_limits.max_notional_exposure,
                },
            )
        )

        if not notional_ok:
            reasons.append("regime_max_notional_exceeded")

        return RiskDecision(
            approved=not reasons,
            reasons=reasons,
            checks=checks,
        )

    def _check_allowed_strategy(
        self,
        proposal: TradeProposal,
        checks: list[GateResult],
        reasons: list[str],
    ) -> None:
        allowed = self.settings.safety.allowed_strategies
        passed = proposal.strategy in allowed
        checks.append(
            GateResult(
                gate="allowed_strategy",
                passed=passed,
                reason=proposal.strategy,
                details={"allowed": allowed},
            )
        )

        if not passed:
            reasons.append("strategy_not_allowed")

    def _check_lot_limit(
        self,
        proposal: TradeProposal,
        checks: list[GateResult],
        reasons: list[str],
    ) -> None:
        max_lots = max((leg.lots for leg in proposal.legs), default=0)
        passed = 0 < max_lots <= self.limits.max_lots_per_order

        checks.append(
            GateResult(
                gate="max_lots_per_order",
                passed=passed,
                reason=f"max_leg_lots={max_lots}",
                details={
                    "max_lots": max_lots,
                    "limit": self.limits.max_lots_per_order,
                },
            )
        )

        if not passed:
            reasons.append("max_lots_exceeded")

    def _check_open_positions(
        self,
        checks: list[GateResult],
        reasons: list[str],
    ) -> None:
        open_count = len(self.positions.get_open_strategy_positions())
        passed = open_count < self.limits.max_open_positions

        checks.append(
            GateResult(
                gate="max_open_positions",
                passed=passed,
                reason=f"open_positions={open_count}",
                details={
                    "open_positions": open_count,
                    "limit": self.limits.max_open_positions,
                },
            )
        )

        if not passed:
            reasons.append("max_open_positions_exceeded")

    def _check_daily_loss(
        self,
        checks: list[GateResult],
        reasons: list[str],
    ) -> None:
        realized_pnl = self.positions.get_daily_realized_pnl()
        passed = realized_pnl > -self.limits.max_daily_loss
        checks.append(
            GateResult(
                gate="max_daily_loss",
                passed=passed,
                reason=f"daily_realized_pnl={realized_pnl:.2f}",
                details={
                    "daily_realized_pnl": realized_pnl,
                    "max_daily_loss": self.limits.max_daily_loss,
                },
            )
        )

        if not passed:
            reasons.append("daily_loss_limit")

    def _check_notional(
        self,
        proposal: TradeProposal,
        features: MarketFeatures,
        checks: list[GateResult],
        reasons: list[str],
    ) -> None:
        notional = sum(
            abs(leg.quantity) * features.spot / 10 for leg in proposal.legs
        )
        passed = notional <= self.limits.max_notional_exposure

        checks.append(
            GateResult(
                gate="max_notional_exposure",
                passed=passed,
                reason=f"notional={notional:.2f}",
                details={
                    "notional": notional,
                    "limit": self.limits.max_notional_exposure,
                },
            )
        )

        if not passed:
            reasons.append("max_notional_exposure_exceeded")

    def _check_defined_risk(
        self,
        proposal: TradeProposal,
        checks: list[GateResult],
        reasons: list[str],
    ) -> None:
        short_legs = [
            leg for leg in proposal.legs if leg.side.value == "SELL"
        ]
        long_legs = [
            leg for leg in proposal.legs if leg.side.value == "BUY"
        ]

        passed = len(short_legs) == 0 or len(long_legs) >= len(short_legs)

        checks.append(
            GateResult(
                gate="defined_risk",
                passed=passed,
                reason=f"short={len(short_legs)},long={len(long_legs)}",
                details={
                    "short_legs": len(short_legs),
                    "long_legs": len(long_legs),
                },
            )
        )

        if not passed:
            reasons.append("undefined_risk_structure")

    def _check_leg_liquidity(
        self,
        proposal: TradeProposal,
        quote_lookup: dict[tuple[str, float], OptionQuote] | None,
        checks: list[GateResult],
        reasons: list[str],
    ) -> None:
        if quote_lookup is None:
            return

        for leg in proposal.legs:
            key = (
                leg.instrument.option_type.value,
                leg.instrument.strike,
            )
            quote = quote_lookup.get(key)

            if quote is None:
                passed = False
                spread = None
                oi = None
                volume = None
            else:
                spread = quote.spread_pct
                oi = quote.oi
                volume = quote.volume
                passed = (
                    spread is not None
                    and spread <= self.limits.max_spread_pct
                    and (oi or 0) >= self.limits.min_oi
                    and (volume or 0) >= self.limits.min_volume
                )

            checks.append(
                GateResult(
                    gate=f"leg_liquidity:{leg.instrument.tradingsymbol}",
                    passed=passed,
                    reason=f"spread={spread},oi={oi},volume={volume}",
                    details={
                        "spread_pct": spread,
                        "oi": oi,
                        "volume": volume,
                    },
                )
            )

            if not passed:
                reasons.append(f"leg_liquidity_failed:{leg.instrument.tradingsymbol}")