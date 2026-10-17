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

    def evaluate(self, features: MarketFeatures) -> GateResult:
        iv_rank = features.iv_rank
        spread = features.iv_rv_spread
        minimum_rank = self.settings.analytics.min_iv_rank
        minimum_spread = self.settings.analytics.min_iv_rv_spread

        passed = (
            iv_rank is not None
            and spread is not None
            and iv_rank >= minimum_rank
            and spread >= minimum_spread
        )

        return GateResult(
            gate="iv_regime",
            passed=passed,
            reason=f"iv_rank={iv_rank},iv_rv_spread={spread}",
            details={
                "iv_rank": iv_rank,
                "iv_rv_spread": spread,
                "min_iv_rank": minimum_rank,
                "min_iv_rv_spread": minimum_spread,
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

        for strike in strikes:
            for option_type in ("CE", "PE"):
                quote = lookup.get((option_type, strike))

                if quote is None:
                    failures.append(f"{option_type}:{strike}:missing")
                    continue

                spread = quote.spread_pct
                oi = quote.oi or 0
                volume = quote.volume or 0

                if (
                    spread is None
                    or spread > limits.max_spread_pct
                    or oi < limits.min_oi
                    or volume < limits.min_volume
                ):
                    failures.append(
                        f"{option_type}:{strike}:spread={spread},oi={oi},volume={volume}"
                    )

        return GateResult(
            gate="strategy_liquidity",
            passed=not failures,
            reason="all_required_legs_liquid" if not failures else "illiquid_legs",
            details={"failures": failures},
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
    ) -> list[GateResult]:
        return [
            self.market_open_gate.evaluate(snapshot),
            self.iv_regime_gate.evaluate(features),
            self.expected_move_gate.evaluate(features),
            self.liquidity_gate.evaluate(snapshot, strikes),
        ]

    @staticmethod
    def all_passed(gates: list[GateResult]) -> bool:
        return all(gate.passed for gate in gates)