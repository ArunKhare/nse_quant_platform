"""Pre-trade strategy gates.

Gates determine whether a strategy is allowed to emit a proposal. They do not
approve execution; risk approval remains a separate concern.
"""

from __future__ import annotations

from typing import Any

from nse_quant.core.models import (
    ChainSnapshot,
    GateResult,
    MarketFeatures,
)
from nse_quant.core.settings import get_settings


class MarketOpenGate:
    def evaluate(self, snapshot: ChainSnapshot) -> GateResult:
        passed = snapshot.is_market_open

        return GateResult(
            gate="market_open",
            passed=passed,
            reason="market_open" if passed else "market_closed",
        )


class IvRegimeGate:
    def __init__(self, settings: Any | None = None) -> None:
        self.settings = settings or get_settings()

    def evaluate(self,features: MarketFeatures,iv_history_count: int | None = None,) -> GateResult:
        expected_move = features.expected_move_points
        buffer = self.settings.analytics.max_expected_move_buffer
        diagnostics = features.diagnostics.get("expected_move_inputs", {})

        analytics = self.settings.analytics
        iv_rank = features.iv_rank
        spread = features.iv_rv_spread

        spread_ok = (
            spread is not None
            and spread >= analytics.min_iv_rv_spread
        )

        has_minimum_history = (
            iv_history_count is not None
            and iv_history_count >= analytics.min_iv_history_observations
        )

        if not has_minimum_history:
            cold_start_allowed = analytics.allow_iv_rank_cold_start
            rank_ok = cold_start_allowed
            mode = "COLD_START"
        else:
            rank_ok = iv_rank is not None and iv_rank >= analytics.min_iv_rank
            mode = "ENFORCED"

        passed = rank_ok and spread_ok

        return GateResult(
            gate="iv_regime",
            passed=passed,
            reason=(
                f"mode={mode}",
                f"iv_history_count={iv_history_count}",
                f"iv_rank={iv_rank}",
                f"iv_rv_spread={spread}",
                f"expected_move_points: {expected_move}",
            ),
            details={
                "mode": mode,
                "iv_history_count": iv_history_count,
                "iv_rank": iv_rank,
                "iv_rv_spread": spread,
                "min_iv_rank": analytics.min_iv_rank,
                "min_iv_rv_spread": analytics.min_iv_rv_spread,
                "min_iv_history_observations": (
                    analytics.min_iv_history_observations
                ),
                "cold_start_allowed": analytics.allow_iv_rank_cold_start,
                "expected_move_points": expected_move,
                "max_buffer": buffer,
                "diagnostics": diagnostics,
            },
        )

class ExpectedMoveGate:
    def __init__(self, settings: Any | None = None) -> None:
        self.settings = settings or get_settings()

    def evaluate(self, features: MarketFeatures) -> GateResult:
        expected_move = features.expected_move_points
        buffer = self.settings.analytics.max_expected_move_buffer

        passed = expected_move is not None and expected_move > 0

        return GateResult(
            gate="expected_move_available",
            passed=passed,
            reason=f"expected_move_points={expected_move}",
            details={
                "expected_move_points": expected_move,
                "max_buffer": buffer,
            },
        )


class LiquidityGate:
    def __init__(self, settings: Any | None = None) -> None:
        self.settings = settings or get_settings()

    def evaluate(
        self,
        snapshot: ChainSnapshot,
        strikes: list[float],
    ) -> GateResult:
        limits = self.settings.risk
        lookup = {
            (quote.instrument.option_type.value, quote.instrument.strike): quote
            for quote in snapshot.quotes
        }

        failures: list[str] = []
        warnings: list[str] = []

        for strike in strikes:
            for option_type in ("CE", "PE"):
                quote = lookup.get((option_type, strike))

                if quote is None:
                    failures.append(f"{option_type}:{strike}:missing")
                    continue

                spread = quote.spread_pct
                oi = quote.oi or 0
                volume = quote.volume or 0

                has_quote = quote.ltp is not None or spread is not None
                has_depth = spread is not None

                if not has_quote:
                    failures.append(f"{option_type}:{strike}:no_quote")
                    continue

                if not has_depth:
                    warnings.append(
                        f"{option_type}:{strike}:missing_bid_ask"
                    )

                if oi < limits.min_oi:
                    failures.append(
                        f"{option_type}:{strike}:low_oi={oi}"
                    )

                if spread is not None and spread > limits.max_spread_pct:
                    failures.append(
                        f"{option_type}:{strike}:wide_spread={spread}"
                    )

                # Volume may be zero for deep OTM wings or outside active trading.
                # Treat it as a warning, not an automatic rejection, when OI and
                # quote data are present.
                if volume < limits.min_volume:
                    warnings.append(
                        f"{option_type}:{strike}:low_volume={volume}"
                    )

        return GateResult(
            gate="strategy_liquidity",
            passed=not failures,
            reason=(
                "all_required_legs_liquid"
                if not failures
                else "illiquid_or_missing_legs"
            ),
            details={
                "failures": failures,
                "warnings": warnings,
            },
        )


class GateEvaluator:
    def __init__(self, settings: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self.market_open_gate = MarketOpenGate()
        self.iv_regime_gate = IvRegimeGate(self.settings)
        self.expected_move_gate = ExpectedMoveGate(self.settings)
        self.liquidity_gate = LiquidityGate(self.settings)

    def evaluate(
        self,
        snapshot: ChainSnapshot,
        features: MarketFeatures,
        strikes: list[float],
        iv_history_count: int | None = None,
    ) -> list[GateResult]:
        return [
            self.market_open_gate.evaluate(snapshot),
            self.iv_regime_gate.evaluate(
                features,
                iv_history_count=iv_history_count,
            ),
            self.expected_move_gate.evaluate(features),
            self.liquidity_gate.evaluate(snapshot, strikes),
        ]

    @staticmethod
    def all_passed(gates: list[GateResult]) -> bool:
        return all(gate.passed for gate in gates)