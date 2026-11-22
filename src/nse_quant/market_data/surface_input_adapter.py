"""Explicit adapter from one persisted operational batch to S2 observations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import date, datetime
from typing import TYPE_CHECKING

from nse_quant.analytics.constant_maturity_inputs import (
    ForwardPoint,
    PremiumPoint,
    SurfaceInputError,
    SurfaceInputs,
    build_surface_inputs,
    constant_maturity,
)
from nse_quant.core.constants import IST

if TYPE_CHECKING:
    from nse_quant.core.models import ChainSnapshot


def surface_from_batch(
    snapshots: Iterable[ChainSnapshot],
    forwards: Iterable[ForwardPoint],
    *,
    expiry_closes: Mapping[date, datetime],
    calendar_reference_id: str,
    as_of: datetime,
    max_age_seconds: float = 300,
    max_source_gap_seconds: float = 30,
) -> SurfaceInputs:
    """Retain the combined-snapshot interface; do not mutate or relabel the batch.

    Caller supplies actual expiry closes from versioned contract/calendar
    evidence and forward records. This adapter does not infer a calendar,
    calculate a synthetic forward, write a store, or authorize an entry.
    """
    batches = list(snapshots)
    if not batches or len({(item.run_id, item.underlying) for item in batches}) != 1:
        raise SurfaceInputError("one_persisted_run_and_underlying_required")
    if not isinstance(calendar_reference_id, str) or not calendar_reference_id.strip():
        raise SurfaceInputError("calendar_reference_required")
    if not isinstance(as_of, datetime) or as_of.utcoffset() is None:
        raise SurfaceInputError("aware_datetime_required")
    closes = set()
    for snapshot in batches:
        if not isinstance(snapshot.ts, datetime) or snapshot.ts.utcoffset() is None or snapshot.ts > as_of:
            raise SurfaceInputError("invalid_or_future_batch_timestamp")
        for quote in snapshot.quotes:
            close = expiry_closes.get(quote.instrument.expiry)
            if (
                not isinstance(close, datetime)
                or close.utcoffset() is None
                or close.astimezone(IST).date() != quote.instrument.expiry
            ):
                raise SurfaceInputError("actual_expiry_close_required")
            closes.add(close)
    brackets = [constant_maturity(((close, 1.0) for close in closes), as_of=as_of, days=days) for days in (30, 90)]
    required = {close for bracket in brackets for close in (bracket.lower_expiry, bracket.upper_expiry)}
    rows = []
    for snapshot in batches:
        for quote in snapshot.quotes:
            instrument = quote.instrument
            if quote.instrument_token != instrument.instrument_token or instrument.underlying != snapshot.underlying:
                raise SurfaceInputError("quote_instrument_identity_mismatch")
            close = expiry_closes.get(instrument.expiry)
            if (
                not isinstance(close, datetime)
                or close.utcoffset() is None
                or close.astimezone(IST).date() != instrument.expiry
            ):
                raise SurfaceInputError("actual_expiry_close_required")
            if close not in required:
                continue
            source = quote.exchange_ts or quote.trade_ts
            if source is None or quote.received_at is None:
                raise SurfaceInputError("genuine_quote_source_and_receive_times_required")
            if quote.bid is None or quote.ask is None:
                raise SurfaceInputError("two_sided_premium_required")
            rows.append(
                PremiumPoint(
                    quote.instrument_token,
                    snapshot.underlying,
                    snapshot.run_id,
                    close,
                    instrument.strike,
                    instrument.option_type.value,
                    quote.bid,
                    quote.ask,
                    source,
                    quote.received_at,
                )
            )
    result = build_surface_inputs(
        rows, forwards, as_of=as_of, max_age_seconds=max_age_seconds, max_source_gap_seconds=max_source_gap_seconds
    )
    return replace(result, calendar_reference_id=calendar_reference_id)
