"""Black-Scholes implied-volatility utilities."""

from __future__ import annotations

import math
from datetime import datetime


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _normal_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def black_scholes_price(
    *,
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    volatility: float,
    option_type: str,
) -> float:
    if time_to_expiry_years <= 0:
        intrinsic = max(0.0, spot - strike)
        if option_type == "PE":
            intrinsic = max(0.0, strike - spot)
        return intrinsic

    sqrt_t = math.sqrt(time_to_expiry_years)
    d1 = (
        math.log(spot / strike) + (risk_free_rate + 0.5 * volatility**2) * time_to_expiry_years
    ) / (volatility * sqrt_t)
    d2 = d1 - volatility * sqrt_t

    if option_type == "CE":
        return spot * _normal_cdf(d1) - strike * math.exp(
            -risk_free_rate * time_to_expiry_years
        ) * _normal_cdf(d2)

    if option_type == "PE":
        return strike * math.exp(-risk_free_rate * time_to_expiry_years) * _normal_cdf(
            -d2
        ) - spot * _normal_cdf(-d1)

    raise ValueError(f"Unsupported option type: {option_type}")


def implied_volatility(
    *,
    option_price: float,
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    option_type: str,
) -> float | None:
    """Solve implied volatility using bracketed bisection."""
    if option_price <= 0 or spot <= 0 or strike <= 0:
        return None

    if time_to_expiry_years <= 0:
        return None

    low, high = 0.0001, 5.0

    low_price = black_scholes_price(
        spot=spot,
        strike=strike,
        time_to_expiry_years=time_to_expiry_years,
        risk_free_rate=risk_free_rate,
        volatility=low,
        option_type=option_type,
    )

    high_price = black_scholes_price(
        spot=spot,
        strike=strike,
        time_to_expiry_years=time_to_expiry_years,
        risk_free_rate=risk_free_rate,
        volatility=high,
        option_type=option_type,
    )

    if not low_price <= option_price <= high_price:
        return None

    for _ in range(100):
        mid = (low + high) / 2

        mid_price = black_scholes_price(
            spot=spot,
            strike=strike,
            time_to_expiry_years=time_to_expiry_years,
            risk_free_rate=risk_free_rate,
            volatility=mid,
            option_type=option_type,
        )

        if abs(mid_price - option_price) < 1e-8:
            return mid

        if mid_price < option_price:
            low = mid
        else:
            high = mid

    return (low + high) / 2


def time_to_expiry_years(
    *,
    as_of: datetime,
    expiry: datetime,
) -> float:
    seconds = (expiry - as_of).total_seconds()
    return max(0.0, seconds / (365.0 * 24.0 * 60.0 * 60.0))
