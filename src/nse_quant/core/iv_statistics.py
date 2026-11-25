"""Canonical rolling IV percentile and rank arithmetic."""

from __future__ import annotations

import math
from collections.abc import Sequence


def iv_percentile_and_rank(
    prior_values: Sequence[float],
    current_value: float,
    *,
    lookback: int = 252,
    minimum_history: int = 120,
) -> tuple[float | None, float | None, int]:
    """Return strict-less IVP and inclusive-current rolling IVR, in percent.

    IVP ranks the current observation against prior observations only. IVR uses
    the most recent lookback-minus-one prior observations plus the current value.
    Both metrics require minimum_history prior observations.
    """
    if (
        type(lookback) is not int
        or type(minimum_history) is not int
        or not 1 <= minimum_history <= lookback
    ):
        raise ValueError("invalid_iv_rank_window_policy")
    if (
        isinstance(current_value, bool)
        or not isinstance(current_value, (int, float))
        or not math.isfinite(current_value)
        or current_value <= 0
    ):
        raise ValueError("invalid_current_iv_value")
    values = list(prior_values[-lookback:])
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
        for value in values
    ):
        raise ValueError("invalid_prior_iv_values")
    rank_window = [*values[-(lookback - 1) :], float(current_value)] if lookback > 1 else [float(current_value)]
    if len(values) < minimum_history:
        return None, None, len(rank_window)
    ivp = 100.0 * sum(value < current_value for value in values) / len(values)
    low, high = min(rank_window), max(rank_window)
    ivr = 100.0 * (current_value - low) / (high - low) if high > low else None
    return ivp, ivr, len(rank_window)
