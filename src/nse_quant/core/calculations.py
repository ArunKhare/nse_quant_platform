"""Canonical, pure calculation primitives shared by analytics, research, and Medallion."""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import datetime

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm

from nse_quant.core.models import MarketRegime

TRADING_DAYS_PER_YEAR = 252
DAYS_PER_YEAR = 365.25
IV_SOLVER_LOW = 0.0001
IV_SOLVER_HIGH = 5.0
IV_SOLVER_XTOL = 1e-10


def time_to_expiry_years(
    *,
    as_of: datetime,
    expiry: datetime,
    days_per_year: float = DAYS_PER_YEAR,
) -> float:
    seconds = (expiry - as_of).total_seconds()
    return max(0.0, seconds / (days_per_year * 86_400))


def black_scholes_price_and_greeks(
    *,
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    implied_volatility: float,
    option_type: str,
) -> tuple[float, float, float, float, float]:
    if min(spot, strike, time_to_expiry_years, implied_volatility) <= 0:
        raise ValueError("Invalid Black-Scholes inputs")
    if option_type not in {"CE", "PE"}:
        raise ValueError("option_type must be CE or PE")

    sqrt_t = math.sqrt(time_to_expiry_years)
    d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * implied_volatility**2) * time_to_expiry_years) / (
        implied_volatility * sqrt_t
    )
    d2 = d1 - implied_volatility * sqrt_t
    discount = math.exp(-risk_free_rate * time_to_expiry_years)
    pdf = norm.pdf(d1)

    if option_type == "CE":
        price = spot * norm.cdf(d1) - strike * discount * norm.cdf(d2)
        delta = norm.cdf(d1)
        theta = (
            -spot * pdf * implied_volatility / (2 * sqrt_t) - risk_free_rate * strike * discount * norm.cdf(d2)
        ) / 365.25
    else:
        price = strike * discount * norm.cdf(-d2) - spot * norm.cdf(-d1)
        delta = norm.cdf(d1) - 1
        theta = (
            -spot * pdf * implied_volatility / (2 * sqrt_t) + risk_free_rate * strike * discount * norm.cdf(-d2)
        ) / 365.25

    gamma = pdf / (spot * implied_volatility * sqrt_t)
    vega = spot * sqrt_t * pdf / 100
    return price, delta, gamma, vega, theta


def implied_volatility(
    *,
    option_price: float,
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    option_type: str,
) -> float | None:
    if min(option_price, spot, strike, time_to_expiry_years) <= 0:
        return None
    if option_type not in {"CE", "PE"}:
        raise ValueError("option_type must be CE or PE")

    discount = math.exp(-risk_free_rate * time_to_expiry_years)
    if option_type == "CE":
        lower = max(0.0, spot - strike * discount)
        upper = spot
    else:
        lower = max(0.0, strike * discount - spot)
        upper = strike

    if not lower < option_price < upper:
        return None

    try:
        return float(
            brentq(
                lambda volatility: (
                    black_scholes_price_and_greeks(
                        spot=spot,
                        strike=strike,
                        time_to_expiry_years=time_to_expiry_years,
                        risk_free_rate=risk_free_rate,
                        implied_volatility=volatility,
                        option_type=option_type,
                    )[0]
                    - option_price
                ),
                IV_SOLVER_LOW,
                IV_SOLVER_HIGH,
                xtol=IV_SOLVER_XTOL,
            )
        )
    except (ValueError, OverflowError, ZeroDivisionError):
        return None


def realized_volatility(
    closes: Iterable[float],
    *,
    window: int,
    trading_days_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float | None:
    if window < 2:
        raise ValueError("window must be at least 2")
    series = pd.Series(list(closes), dtype=float).dropna()
    if len(series) < window + 1:
        return None
    returns = series.tail(window + 1).pct_change().dropna()
    if returns.empty:
        return None
    return float(returns.std(ddof=1) * math.sqrt(trading_days_per_year))


def iv_rank(
    current_iv: float | None,
    history: Iterable[float],
) -> float | None:
    if current_iv is None or not np.isfinite(current_iv) or current_iv <= 0:
        return None
    values = np.asarray(list(history), dtype=float)
    values = values[np.isfinite(values) & (values > 0)]
    if values.size == 0:
        return None
    low = float(values.min())
    high = float(values.max())
    if high <= low:
        return 50.0
    return float(np.clip((current_iv - low) / (high - low) * 100, 0, 100))


def iv_percentile(
    current_iv: float | None,
    history: Iterable[float],
) -> float | None:
    if current_iv is None or not np.isfinite(current_iv) or current_iv <= 0:
        return None
    values = np.asarray(list(history), dtype=float)
    values = values[np.isfinite(values) & (values > 0)]
    if values.size == 0:
        return None
    return float((values < current_iv).mean() * 100)


def atm_iv(
    iv_by_strike: dict[float, float | None],
    spot: float,
) -> float | None:
    valid = {strike: iv for strike, iv in iv_by_strike.items() if iv is not None and np.isfinite(iv) and iv > 0}
    if not valid:
        return None
    atm_strike = min(valid, key=lambda strike: abs(strike - spot))
    return float(valid[atm_strike])


def classify_market_regime(
    *,
    spot: float,
    fast_sma: float | None,
    slow_sma: float | None,
    realized_volatility: float | None,
    volatile_rv_threshold: float = 0.35,
    trend_up_tolerance: float = 1.002,
    trend_down_tolerance: float = 0.998,
) -> MarketRegime:
    if realized_volatility is not None and realized_volatility > volatile_rv_threshold:
        return MarketRegime.VOLATILE
    if fast_sma is None or slow_sma is None:
        return MarketRegime.UNKNOWN
    if fast_sma > slow_sma * trend_up_tolerance:
        return MarketRegime.TREND_UP
    if fast_sma < slow_sma * trend_down_tolerance:
        return MarketRegime.TREND_DOWN
    return MarketRegime.RANGE
