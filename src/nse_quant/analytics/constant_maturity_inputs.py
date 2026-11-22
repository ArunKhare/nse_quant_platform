"""Observational S2 surface inputs from timestamped premiums and forwards.

No stored BSM IV/delta is reused as Black-76 evidence. Forward delta means
undiscounted d(option forward value)/dF: N(d1) for calls and N(d1)-1 for puts.
Expiry-close instants and matching forward evidence are explicit inputs.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from statistics import NormalDist
from typing import Literal

VERSION = "constant_maturity_black76_inputs_v1"
DELTA_CONVENTION = "black76_undiscounted_forward_delta_v1"
YEAR_SECONDS = 365 * 86400
NORMAL = NormalDist()


class SurfaceInputError(ValueError):
    """Input cannot establish this observational surface contract."""


def _positive(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
        raise SurfaceInputError(f"invalid_positive_value:{name}")
    return float(value)


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise SurfaceInputError("aware_datetime_required")
    return value.astimezone(UTC)


def _fresh(source: datetime, received: datetime, as_of: datetime, max_age: float) -> None:
    source, received, as_of = _utc(source), _utc(received), _utc(as_of)
    if source > received or received > as_of or (as_of - source).total_seconds() > max_age:
        raise SurfaceInputError("future_stale_or_unordered_timestamp")


@dataclass(frozen=True)
class PremiumPoint:
    token: int
    underlying: str
    batch_id: str
    expiry_close: datetime
    strike: float
    option_type: str
    bid: float
    ask: float
    source_time: datetime
    received_at: datetime


@dataclass(frozen=True)
class ForwardPoint:
    underlying: str
    expiry_close: datetime
    forward: float
    rate: float
    source_time: datetime
    received_at: datetime
    source: str
    reference_id: str


@dataclass(frozen=True)
class ConstantMaturityValue:
    days: int
    iv: float
    lower_expiry: datetime
    upper_expiry: datetime
    upper_weight: float


@dataclass(frozen=True)
class SurfaceInputs:
    underlying: str
    batch_id: str
    as_of: datetime
    source_time: datetime
    received_at: datetime
    iv30: ConstantMaturityValue
    iv90: ConstantMaturityValue
    call25_30: ConstantMaturityValue
    put25_30: ConstantMaturityValue
    rr25: float
    used_tokens: tuple[int, ...]
    forward_reference_ids: tuple[str, ...]
    calendar_reference_id: str | None = None
    version: str = VERSION
    delta_convention: str = DELTA_CONVENTION
    iv_source: str = "internal_cm"
    mode: str = "observation"
    decision_eligibility_asserted: Literal[False] = False


def black76_price(
    forward: float, strike: float, years: float, rate: float, volatility: float, option_type: str
) -> float:
    forward, strike, years, volatility = (
        _positive(value, name)
        for value, name in ((forward, "forward"), (strike, "strike"), (years, "years"), (volatility, "iv"))
    )
    if isinstance(rate, bool) or not isinstance(rate, (float, int)) or not math.isfinite(rate) or abs(rate) > 1:
        raise SurfaceInputError("invalid_rate")
    if option_type not in {"CE", "PE"}:
        raise SurfaceInputError("invalid_option_type")
    root = volatility * math.sqrt(years)
    d1 = (math.log(forward / strike) + root * root / 2) / root
    d2 = d1 - root
    discount = math.exp(-rate * years)
    if forward >= strike:
        put = strike * NORMAL.cdf(-d2) - forward * NORMAL.cdf(-d1)
        call = put + forward - strike
    else:
        call = forward * NORMAL.cdf(d1) - strike * NORMAL.cdf(d2)
        put = call + strike - forward
    return discount * (call if option_type == "CE" else put)


def black76_iv(price: float, forward: float, strike: float, years: float, rate: float, option_type: str) -> float:
    _positive(price, "premium")
    # Validate the domain through the same versioned pricing primitive.
    low, high = 0.000001, 5.0
    low_price = black76_price(forward, strike, years, rate, low, option_type)
    high_price = black76_price(forward, strike, years, rate, high, option_type)
    if not low_price < price < high_price or high_price - low_price <= 1e-8:
        raise SurfaceInputError("premium_outside_identifiable_black76_bracket")
    for _ in range(100):
        mid = (low + high) / 2
        candidate = black76_price(forward, strike, years, rate, mid, option_type)
        if candidate < price:
            low = mid
        else:
            high = mid
    result = (low + high) / 2
    tolerance = 1e-8 + abs(price) * 1e-10
    if abs(black76_price(forward, strike, years, rate, result, option_type) - price) > tolerance:
        raise SurfaceInputError("black76_residual_not_supported")
    return result


def black76_forward_delta(forward: float, strike: float, years: float, volatility: float, option_type: str) -> float:
    for value, name in ((forward, "forward"), (strike, "strike"), (years, "years"), (volatility, "iv")):
        _positive(value, name)
    if option_type not in {"CE", "PE"}:
        raise SurfaceInputError("invalid_option_type")
    root = volatility * math.sqrt(years)
    d1 = (math.log(forward / strike) + root * root / 2) / root
    return NORMAL.cdf(d1) - (1 if option_type == "PE" else 0)


def _interpolate(points: list[tuple[float, float]], target: float) -> float:
    ordered = sorted(points)
    if len({x for x, _ in ordered}) != len(ordered):
        raise SurfaceInputError("duplicate_interpolation_coordinate")
    for x, value in ordered:
        if x == target:
            return value
    for (left, lv), (right, rv) in zip(ordered, ordered[1:], strict=False):
        if left < target < right:
            return lv + (rv - lv) * (target - left) / (right - left)
    raise SurfaceInputError("interpolation_bracket_missing_no_extrapolation")


def synthetic_forward_from_pair(
    call: PremiumPoint,
    put: PremiumPoint,
    *,
    as_of: datetime,
    rate: float,
    max_age_seconds: float = 300,
    max_source_gap_seconds: float = 30,
) -> ForwardPoint:
    """Explicit same-strike put/call parity forward; never substitute spot.

    F = K + exp(rT) * (call_mid - put_mid). Spread/no-arbitrage admission is
    separate; the exact pair and assumptions are fingerprinted for observation.
    """
    as_of = _utc(as_of)
    max_age_seconds = _positive(max_age_seconds, "max_age_seconds")
    if (
        isinstance(max_source_gap_seconds, bool)
        or not isinstance(max_source_gap_seconds, (float, int))
        or not math.isfinite(max_source_gap_seconds)
        or max_source_gap_seconds < 0
    ):
        raise SurfaceInputError("invalid_source_gap")
    if (
        call.option_type != "CE"
        or put.option_type != "PE"
        or not call.batch_id
        or not call.underlying
        or (call.batch_id, call.underlying, _utc(call.expiry_close), call.strike)
        != (put.batch_id, put.underlying, _utc(put.expiry_close), put.strike)
        or type(call.token) is not int
        or type(put.token) is not int
        or min(call.token, put.token) <= 0
        or call.token == put.token
    ):
        raise SurfaceInputError("matched_call_put_pair_required")
    if isinstance(rate, bool) or not isinstance(rate, (float, int)) or not math.isfinite(rate) or abs(rate) > 1:
        raise SurfaceInputError("invalid_rate")
    strike = _positive(call.strike, "strike")
    years = _positive((_utc(call.expiry_close) - as_of).total_seconds() / YEAR_SECONDS, "years")
    mids = []
    for quote in (call, put):
        _fresh(quote.source_time, quote.received_at, as_of, max_age_seconds)
        bid, ask = _positive(quote.bid, "bid"), _positive(quote.ask, "ask")
        if ask < bid:
            raise SurfaceInputError("crossed_market")
        mids.append((bid + ask) / 2)
    if abs((_utc(call.source_time) - _utc(put.source_time)).total_seconds()) > max_source_gap_seconds:
        raise SurfaceInputError("source_observation_gap_exceeded")
    forward = _positive(strike + math.exp(rate * years) * (mids[0] - mids[1]), "synthetic_forward")
    fingerprint = hashlib.sha256(
        json.dumps(
            {"call": asdict(call), "put": asdict(put), "rate": rate, "version": VERSION},
            sort_keys=True,
            separators=(",", ":"),
            default=lambda value: value.isoformat(),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    return ForwardPoint(
        call.underlying,
        _utc(call.expiry_close),
        forward,
        rate,
        min(_utc(call.source_time), _utc(put.source_time)),
        max(_utc(call.received_at), _utc(put.received_at)),
        "synthetic_put_call_parity_mid_v1",
        fingerprint,
    )


def constant_maturity(points: Iterable[tuple[datetime, float]], *, as_of: datetime, days: int) -> ConstantMaturityValue:
    as_of = _utc(as_of)
    if type(days) is not int or days < 7:
        raise SurfaceInputError("target_days_must_be_integer_at_least_7")
    values = [(_utc(expiry), _positive(iv, "iv")) for expiry, iv in points]
    if len({expiry for expiry, _ in values}) != len(values):
        raise SurfaceInputError("duplicate_expiry")
    eligible = sorted((expiry, iv) for expiry, iv in values if expiry - as_of >= timedelta(days=7))
    target = as_of + timedelta(days=days)
    for expiry, iv in eligible:
        if expiry == target:
            return ConstantMaturityValue(days, iv, expiry, expiry, 0.0)
    for (left, lv), (right, rv) in zip(eligible, eligible[1:], strict=False):
        if left < target < right:
            lt, rt, tt = ((instant - as_of).total_seconds() / YEAR_SECONDS for instant in (left, right, target))
            weight = (tt - lt) / (rt - lt)
            variance = ((1 - weight) * lv * lv * lt + weight * rv * rv * rt) / tt
            return ConstantMaturityValue(days, math.sqrt(variance), left, right, weight)
    raise SurfaceInputError("maturity_bracket_missing_no_extrapolation")


def build_surface_inputs(
    quotes: Iterable[PremiumPoint],
    forwards: Iterable[ForwardPoint],
    *,
    as_of: datetime,
    max_age_seconds: float = 300,
    max_source_gap_seconds: float = 30,
) -> SurfaceInputs:
    """Build observational ATM-forward IV30/IV90 and 30D call-minus-put RR25.

    Uses two-sided mid premiums and Black-76 IV, IV interpolation in strike
    space at the forward for ATM, and in absolute forward-delta space for RR25.
    Call/put wing variances are maturity-interpolated separately, never RR25.
    No BSM, spot, nearest-wing, maturity or stale-data substitution is allowed.
    """
    as_of = _utc(as_of)
    max_age_seconds = _positive(max_age_seconds, "max_age_seconds")
    if (
        isinstance(max_source_gap_seconds, bool)
        or not isinstance(max_source_gap_seconds, (float, int))
        or not math.isfinite(max_source_gap_seconds)
        or max_source_gap_seconds < 0
    ):
        raise SurfaceInputError("invalid_source_gap")
    rows, frows = list(quotes), list(forwards)
    if not rows:
        raise SurfaceInputError("empty_surface_batch")
    batch, underlying = rows[0].batch_id, rows[0].underlying
    if not batch or not underlying or any(q.batch_id != batch or q.underlying != underlying for q in rows):
        raise SurfaceInputError("mixed_or_missing_batch_identity")
    if any(type(q.token) is not int or q.token <= 0 for q in rows) or len({q.token for q in rows}) != len(rows):
        raise SurfaceInputError("invalid_or_duplicate_instrument_token")
    expiries = {_utc(q.expiry_close) for q in rows}
    # Bracket selection does not claim that the selected quotes are valid yet.
    b30 = constant_maturity(((expiry, 1.0) for expiry in expiries), as_of=as_of, days=30)
    b90 = constant_maturity(((expiry, 1.0) for expiry in expiries), as_of=as_of, days=90)
    required = {b30.lower_expiry, b30.upper_expiry, b90.lower_expiry, b90.upper_expiry}
    fmap: dict[datetime, ForwardPoint] = {}
    for point in frows:
        expiry = _utc(point.expiry_close)
        if expiry not in required:
            continue
        if expiry in fmap:
            raise SurfaceInputError("duplicate_forward_expiry")
        if point.underlying != underlying or not point.source or not point.reference_id:
            raise SurfaceInputError("invalid_forward_identity")
        _positive(point.forward, "forward")
        _fresh(point.source_time, point.received_at, as_of, max_age_seconds)
        fmap[expiry] = point
    if set(fmap) != required:
        raise SurfaceInputError("matching_expiry_forward_missing")
    used = [q for q in rows if _utc(q.expiry_close) in required]
    times = [_utc(fmap[expiry].source_time) for expiry in required]
    receipts = [_utc(fmap[expiry].received_at) for expiry in required]
    atm_points: list[tuple[datetime, float]] = []
    call_points: list[tuple[datetime, float]] = []
    put_points: list[tuple[datetime, float]] = []
    for expiry in sorted(required):
        forward = fmap[expiry]
        years = (expiry - as_of).total_seconds() / YEAR_SECONDS
        smile: dict[tuple[str, float], tuple[float, float]] = {}
        for quote in used:
            if _utc(quote.expiry_close) != expiry:
                continue
            _fresh(quote.source_time, quote.received_at, as_of, max_age_seconds)
            times.append(_utc(quote.source_time))
            receipts.append(_utc(quote.received_at))
            strike = _positive(quote.strike, "strike")
            bid, ask = _positive(quote.bid, "bid"), _positive(quote.ask, "ask")
            if ask < bid:
                raise SurfaceInputError("crossed_market")
            key = (quote.option_type, strike)
            if key in smile:
                raise SurfaceInputError("duplicate_expiry_type_strike")
            iv = black76_iv((bid + ask) / 2, forward.forward, strike, years, forward.rate, quote.option_type)
            delta = abs(black76_forward_delta(forward.forward, strike, years, iv, quote.option_type))
            smile[key] = (iv, delta)
        otm = [
            (strike, iv)
            for (kind, strike), (iv, _) in smile.items()
            if (kind == "PE" and strike < forward.forward) or (kind == "CE" and strike >= forward.forward)
        ]
        atm_points.append((expiry, _interpolate(otm, forward.forward)))
        if expiry in {b30.lower_expiry, b30.upper_expiry}:
            for kind, target in (("CE", call_points), ("PE", put_points)):
                wing = [(delta, iv) for (option_type, _), (iv, delta) in smile.items() if option_type == kind]
                target.append((expiry, _interpolate(wing, 0.25)))
    if (max(times) - min(times)).total_seconds() > max_source_gap_seconds:
        raise SurfaceInputError("source_observation_gap_exceeded")
    iv30 = constant_maturity(atm_points, as_of=as_of, days=30)
    iv90 = constant_maturity(atm_points, as_of=as_of, days=90)
    call25 = constant_maturity(call_points, as_of=as_of, days=30)
    put25 = constant_maturity(put_points, as_of=as_of, days=30)
    return SurfaceInputs(
        underlying,
        batch,
        as_of,
        min(times),
        max(receipts),
        iv30,
        iv90,
        call25,
        put25,
        call25.iv - put25.iv,
        tuple(sorted(q.token for q in used)),
        tuple(fmap[expiry].reference_id for expiry in sorted(required)),
    )
