"""Regime-level reporting for deterministic vectorbt backtests."""

from __future__ import annotations

from typing import Any


def add_regime_reporting(
    result: dict[str, Any],
    regimes: dict[str, str],
) -> dict[str, Any]:
    """Attach observational regime-level reporting to a vectorbt result."""
    by_regime: dict[str, dict[str, float | int]] = {}

    for point in result["equity_curve"]:
        regime = regimes.get(point["ts"], "UNKNOWN")
        bucket = by_regime.setdefault(
            regime,
            {
                "points": 0,
                "start_equity": point["equity"],
                "end_equity": point["equity"],
            },
        )
        bucket["points"] += 1
        bucket["end_equity"] = point["equity"]

    for bucket in by_regime.values():
        start = float(bucket["start_equity"])
        end = float(bucket["end_equity"])
        bucket["return"] = end / start - 1.0 if start else 0.0

    result["regime_reporting"] = by_regime
    return result
