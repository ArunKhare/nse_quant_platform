"""Exact research price geometry over stored binary64; no market-validity claims."""

from __future__ import annotations

import math
from fractions import Fraction

FEATURE_VERSION = "legacy-stored-price-geometry@1"
MAX_CELL_BYTES = 65536


class GeometryRejected(ValueError):
    """Fixed diagnostic codes, never raw source content."""


def _number(value: object) -> Fraction | None:
    if value is None:
        return None
    if type(value) is not str:
        raise GeometryRejected("EXACT_STORED_FINITE_BINARY64_REQUIRED")
    try:
        if len(value.encode()) > MAX_CELL_BYTES:
            raise GeometryRejected("EXACT_STORED_FINITE_BINARY64_REQUIRED")
        number = float.fromhex(value)
    except (ValueError, OverflowError):
        raise GeometryRejected("EXACT_STORED_FINITE_BINARY64_REQUIRED") from None
    if not math.isfinite(number) or number.hex() != value:
        raise GeometryRejected("EXACT_STORED_FINITE_BINARY64_REQUIRED")
    return Fraction.from_float(number)


def _ratio(value: Fraction | None) -> dict[str, object]:
    if value is None:
        return dict(status="UNAVAILABLE", numerator=None, denominator=None)
    return dict(
        status="COMPUTED", numerator=str(value.numerator), denominator=str(value.denominator)
    )


def price_geometry(fields: dict[str, object], *, table: str) -> dict[str, object]:
    """Content-only kernel. Supplied fields do not attest a native source.

    Ratios represent arithmetic on exact stored floats, NOT recovered exchange
    tick precision. Rational zero does not preserve signed zero; source bytes do.
    Invalid market geometry is flagged, not silently repaired or market-approved.
    """
    if type(fields) is not dict or table not in ("spot_candles", "option_stream"):
        raise GeometryRejected("SUPPORTED_STORED_PRICE_PROFILE_REQUIRED")
    required = (
        ("open", "high", "low", "close")
        if table == "spot_candles"
        else ("bid", "ask", "ltp", "spot", "strike")
    )
    if not set(required) <= fields.keys():
        raise GeometryRejected("EXPLICIT_PRICE_FIELDS_REQUIRED")
    values = {name: _number(fields[name]) for name in required}
    flags: list[str] = []
    for name in required:
        value = values[name]
        if value is None:
            flags.append("MISSING_" + name.upper())
        elif value < 0:
            flags.append("NEGATIVE_" + name.upper())
        elif value == 0:
            flags.append("ZERO_" + name.upper())
    results: dict[str, dict[str, object]] = {}
    if table == "spot_candles":
        opening, high, low, close = (values[k] for k in required)
        results["high_minus_low"] = _ratio(None if high is None or low is None else high - low)
        results["close_minus_open"] = _ratio(
            None if close is None or opening is None else close - opening
        )
        results["upper_shadow"] = _ratio(
            None if high is None or opening is None or close is None else high - max(opening, close)
        )
        results["lower_shadow"] = _ratio(
            None if low is None or opening is None or close is None else min(opening, close) - low
        )
        if high is not None and low is not None and high < low:
            flags.append("INVERTED_HIGH_LOW")
        for name in ("open", "close"):
            value = values[name]
            if value is not None and (
                (high is not None and value > high) or (low is not None and value < low)
            ):
                flags.append(name.upper() + "_OUTSIDE_STORED_RANGE")
    else:
        bid, ask, ltp, spot, strike = (values[k] for k in required)
        midpoint = None if bid is None or ask is None else (bid + ask) / 2
        results["ask_minus_bid"] = _ratio(None if bid is None or ask is None else ask - bid)
        results["bid_ask_midpoint"] = _ratio(midpoint)
        results["ltp_minus_midpoint"] = _ratio(
            None if ltp is None or midpoint is None else ltp - midpoint
        )
        results["spot_minus_strike"] = _ratio(
            None if spot is None or strike is None else spot - strike
        )
        if bid is not None and ask is not None and ask < bid:
            flags.append("CROSSED_STORED_BID_ASK")
        if ltp is not None and ((bid is not None and ltp < bid) or (ask is not None and ltp > ask)):
            flags.append("LTP_OUTSIDE_STORED_BID_ASK")
    return dict(feature_version=FEATURE_VERSION, features=results, quality_flags=flags)
