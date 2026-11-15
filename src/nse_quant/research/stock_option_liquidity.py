"""Stock-option liquidity thresholds; research-only evaluator, no execution authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LiquidityThresholds:
    max_spread_pct: float = 2.0
    min_depth: int = 50
    min_oi: int = 1000
    min_volume: int = 100


def evaluate_liquidity(
    *,
    bid: float | None,
    ask: float | None,
    depth: int | None,
    open_interest: int | None,
    volume: int | None,
    settings: LiquidityThresholds | None = None,
) -> dict[str, Any]:
    """Evaluate stock-option liquidity against thresholds; observational only."""
    settings = settings or LiquidityThresholds()
    failures: list[str] = []

    spread_pct: float | None = None
    if bid is not None and ask is not None and bid > 0:
        spread_pct = (ask - bid) / bid * 100.0
        if spread_pct > settings.max_spread_pct:
            failures.append("spread_too_wide")
    else:
        failures.append("missing_or_invalid_quote")

    if depth is None or depth < settings.min_depth:
        failures.append("insufficient_depth")
    if open_interest is None or open_interest < settings.min_oi:
        failures.append("insufficient_open_interest")
    if volume is None or volume < settings.min_volume:
        failures.append("insufficient_volume")

    tradable = not failures
    return {
        "available": True,
        "tradable": tradable,
        "spread_pct": spread_pct,
        "failures": failures,
        "settings": {
            "max_spread_pct": settings.max_spread_pct,
            "min_depth": settings.min_depth,
            "min_oi": settings.min_oi,
            "min_volume": settings.min_volume,
        },
        "decision_eligibility_asserted": False,
    }


def classify_liquidity(result: dict[str, Any]) -> str:
    """Classify liquidity as LIQUID, MARGINAL, or ILLIQUID from an evaluate_liquidity result."""
    if not result.get("available"):
        return "ILLIQUID"
    failures = result.get("failures", [])
    if not failures:
        return "LIQUID"
    if len(failures) == 1 and failures[0] == "spread_too_wide":
        return "MARGINAL"
    return "ILLIQUID"
