"""Black-Scholes analytics."""

from __future__ import annotations

import math
from datetime import date, datetime, time

from scipy.optimize import brentq
from scipy.stats import norm

from ..core.constants import IV_SOLVER_HIGH, IV_SOLVER_LOW


def bs_price_greeks(
    spot: float, strike: float, ttm: float, rate: float, iv: float, option_type: str
):
    if min(spot, strike, ttm, iv) <= 0:
        raise ValueError("Invalid BS inputs")
    st = math.sqrt(ttm)
    d1 = (math.log(spot / strike) + (rate + 0.5 * iv * iv) * ttm) / (iv * st)
    d2 = d1 - iv * st
    disc = math.exp(-rate * ttm)
    pdf = norm.pdf(d1)
    if option_type == "CE":
        price = spot * norm.cdf(d1) - strike * disc * norm.cdf(d2)
        delta = norm.cdf(d1)
        theta = (-spot * pdf * iv / (2 * st) - rate * strike * disc * norm.cdf(d2)) / 365.25
    else:
        price = strike * disc * norm.cdf(-d2) - spot * norm.cdf(-d1)
        delta = norm.cdf(d1) - 1
        theta = (-spot * pdf * iv / (2 * st) + rate * strike * disc * norm.cdf(-d2)) / 365.25
    return price, delta, pdf / (spot * iv * st), spot * st * pdf / 100, theta


def implied_volatility(
    price: float, spot: float, strike: float, ttm: float, rate: float, option_type: str
) -> float | None:
    if min(price, spot, strike, ttm) <= 0:
        return None
    disc = math.exp(-rate * ttm)
    lower = max(0, spot - strike * disc) if option_type == "CE" else max(0, strike * disc - spot)
    upper = spot if option_type == "CE" else strike * disc
    if not lower < price < upper:
        return None
    try:
        return float(
            brentq(
                lambda v: bs_price_greeks(spot, strike, ttm, rate, v, option_type)[0] - price,
                IV_SOLVER_LOW,
                IV_SOLVER_HIGH,
                xtol=1e-10,
            )
        )
    except (ValueError, OverflowError, ZeroDivisionError):
        return None


def enrich_quote(quote, spot: float, expiry: date | datetime, now: datetime, rate: float):
    expiry_datetime = (
        expiry
        if isinstance(expiry, datetime)
        else datetime.combine(expiry, time.max, tzinfo=now.tzinfo)
    )
    ttm = max((expiry_datetime - now).total_seconds() / (365.25 * 86400), 0)
    price = quote.mid or quote.ltp
    iv = (
        implied_volatility(
            price, spot, quote.instrument.strike, ttm, rate, quote.instrument.option_type.value
        )
        if price
        else None
    )
    if iv:
        _, quote.delta, quote.gamma, quote.vega, quote.theta = bs_price_greeks(
            spot, quote.instrument.strike, ttm, rate, iv, quote.instrument.option_type.value
        )
    quote.iv = iv
    return quote
