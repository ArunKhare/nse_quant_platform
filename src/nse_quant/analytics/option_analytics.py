"""Black-Scholes analytics using canonical calculation primitives.
Option-stream feature calculation.

This module enriches each option-chain quote during live option-stream capture
and derives chain-level Gold features after the corresponding option-stream
snapshot has been normalized into Silver.

Per-contract features
---------------------

For every option contract in a snapshot, the following analytics are calculated
from the option quote, underlying spot, expiry, strike, option type, and
configured risk-free rate:

- ``iv``: Implied volatility.
- ``delta``: Sensitivity of option price to underlying spot.
- ``gamma``: Rate of change of delta with respect to spot.
- ``vega``: Sensitivity of option price to implied volatility.
- ``theta``: Time-decay sensitivity of option price.

These values are persisted in the legacy ``option_stream`` table alongside
``spot``, ``ltp``, ``bid``, ``ask``, ``volume``, ``oi``, ``quote_status``, and
the raw payload.

Chain-level Gold features
-------------------------

After Silver normalization, one Gold feature record is built per Silver
revision. It aggregates the valid CE and PE observations in that snapshot:

- ``atm_strike``: Strike of the call closest to spot, or the put closest to
  spot when no usable call is available.
- ``atm_iv``: Implied volatility of the nearest-strike call, falling back to
  the nearest-strike put when call IV is unavailable.
- ``call_oi``: Total open interest across CE contracts.
- ``put_oi``: Total open interest across PE contracts.
- ``pcr``: Put-call ratio, calculated as ``put_oi / call_oi``.
- ``total_volume``: Total volume across all CE and PE contracts.
- ``straddle``: ATM call LTP plus ATM put LTP.
- ``expected_move``: ATM straddle divided by underlying spot.
- ``observation_count``: Number of option-chain observations in the revision.
- ``quality_status``: ``VALID`` when no observations were quarantined;
  otherwise ``QUARANTINED``.
 The capture runner src/nse_quant/market_data/kite_stream.py calls the analytics module
Scope
-----

This module does not calculate daily IV, IV rank, realized volatility, SMA,
ATR, regime classification, skew, term structure, strategy eligibility, or
decision eligibility. Missing inputs remain null; no gap filling, publication,
or trading authority is asserted.
"""

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
