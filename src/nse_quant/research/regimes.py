"""Point-in-time market-regime classification."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class RegimeClassification:
    trend_regime: str
    volatility_regime: str
    iv_regime: str
    regime: str
    features: dict[str, float | None]


def classify_trend(
    close: float,
    sma50: float | None,
    atr14: float | None,
) -> str:
    if sma50 is None or atr14 is None or atr14 <= 0:
        return "UNKNOWN"

    normalized_distance = (close - sma50) / atr14

    if normalized_distance >= 1.0:
        return "BULL"
    if normalized_distance <= -1.0:
        return "BEAR"
    return "RANGE"


def classify_volatility(
    realized_volatility: float | None,
    rolling_percentile: float | None,
) -> str:
    if realized_volatility is None or rolling_percentile is None:
        return "UNKNOWN"

    if rolling_percentile >= 80:
        return "HIGH"
    if rolling_percentile <= 20:
        return "LOW"
    return "NORMAL"


def classify_iv(
    iv_rank: float | None,
    iv_percentile: float | None,
) -> str:
    rank = (
        iv_percentile
        if iv_percentile is not None
        else iv_rank
    )

    if rank is None:
        return "UNKNOWN"

    if rank >= 70:
        return "HIGH"
    if rank <= 30:
        return "LOW"
    return "NORMAL"


def combine_regime(
    trend_regime: str,
    volatility_regime: str,
    iv_regime: str,
) -> str:
    if trend_regime == "UNKNOWN":
        return "UNKNOWN"

    return f"{trend_regime}|{iv_regime}"


def classify_regime(
    *,
    close: float,
    sma50: float | None,
    atr14: float | None,
    realized_volatility: float | None,
    rv_percentile: float | None,
    iv_rank: float | None,
    iv_percentile: float | None,
) -> RegimeClassification:
    trend_regime = classify_trend(close, sma50, atr14)
    volatility_regime = classify_volatility(
        realized_volatility,
        rv_percentile,
    )
    iv_regime = classify_iv(iv_rank, iv_percentile)

    return RegimeClassification(
        trend_regime=trend_regime,
        volatility_regime=volatility_regime,
        iv_regime=iv_regime,
        regime=combine_regime(
            trend_regime,
            volatility_regime,
            iv_regime,
        ),
        features={
            "close": close,
            "sma50": sma50,
            "atr14": atr14,
            "normalized_trend_distance": (
                (close - sma50) / atr14
                if sma50 is not None and atr14 and atr14 > 0
                else None
            ),
            "realized_volatility": realized_volatility,
            "rv_percentile": rv_percentile,
            "iv_rank": iv_rank,
            "iv_percentile": iv_percentile,
        },
    )


def rolling_percentile(
    series: pd.Series,
    window: int = 252,
) -> pd.Series:
    """Return each value's percentile within its trailing window."""
    return series.rolling(
        window=window,
        min_periods=30,
    ).apply(
        lambda values: (
            (values[-1] > values[:-1]).mean() * 100
            if len(values) > 1
            else float("nan")
        ),
        raw=True,
    )