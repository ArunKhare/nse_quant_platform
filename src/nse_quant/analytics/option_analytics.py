"""Black-Scholes analytics using canonical calculation primitives."""

from __future__ import annotations

from datetime import date, datetime, time

from nse_quant.core.calculations import (
    black_scholes_price_and_greeks,
    time_to_expiry_years,
)
from nse_quant.core.calculations import (
    implied_volatility as canonical_implied_volatility,
)


def bs_price_greeks(
    spot: float,
    strike: float,
    ttm: float,
    rate: float,
    iv: float,
    option_type: str,
):
    """Compatibility wrapper around the canonical Black-Scholes primitive."""
    return black_scholes_price_and_greeks(
        spot=spot,
        strike=strike,
        time_to_expiry_years=ttm,
        risk_free_rate=rate,
        implied_volatility=iv,
        option_type=option_type,
    )


def implied_volatility(
    price: float,
    spot: float,
    strike: float,
    ttm: float,
    rate: float,
    option_type: str,
) -> float | None:
    """Compatibility wrapper around the canonical implied-volatility primitive."""
    return canonical_implied_volatility(
        option_price=price,
        spot=spot,
        strike=strike,
        time_to_expiry_years=ttm,
        risk_free_rate=rate,
        option_type=option_type,
    )


def enrich_quote(
    quote,
    spot: float,
    expiry: date | datetime,
    now: datetime,
    rate: float,
):
    expiry_datetime = expiry if isinstance(expiry, datetime) else datetime.combine(expiry, time.max, tzinfo=now.tzinfo)

    ttm = time_to_expiry_years(
        as_of=now,
        expiry=expiry_datetime,
    )

    price = quote.mid or quote.ltp

    iv = (
        implied_volatility(
            price=price,
            spot=spot,
            strike=quote.instrument.strike,
            ttm=ttm,
            rate=rate,
            option_type=quote.instrument.option_type.value,
        )
        if price
        else None
    )

    if iv:
        _, quote.delta, quote.gamma, quote.vega, quote.theta = bs_price_greeks(
            spot=spot,
            strike=quote.instrument.strike,
            ttm=ttm,
            rate=rate,
            iv=iv,
            option_type=quote.instrument.option_type.value,
        )

    quote.iv = iv
    return quote
