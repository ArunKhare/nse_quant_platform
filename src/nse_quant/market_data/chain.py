"""Dynamic NFO chain discovery with explicit replayable expiry selection."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any

from ..core.constants import CE, IST, PE
from ..core.models import ChainSnapshot, Instrument, OptionQuote, OptionType
from .expiry_selection import select_capture_expiries


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def discover_chain(
    instruments: Iterable[dict[str, Any]],
    underlying: str,
    spot: float,
    expiry: date | None = None,
    strikes_per_side: int = 10,
    *,
    as_of: date | None = None,
) -> tuple[date, list[Instrument]]:
    today = as_of if as_of is not None else datetime.now(IST).date()
    rows = [r for r in instruments
            if r.get("name") == underlying and r.get("instrument_type") in {CE, PE}]
    if not rows:
        raise ValueError(f"No NFO options for {underlying}")
    expiries = sorted({_as_date(r["expiry"]) for r in rows
                       if _as_date(r["expiry"]) >= today})
    if not expiries:
        raise ValueError(f"No unexpired NFO options for {underlying}")
    selected_expiry = expiry if expiry is not None else expiries[0]
    if selected_expiry not in expiries:
        raise ValueError(f"Expiry unavailable: {selected_expiry}")
    selected = [r for r in rows if _as_date(r["expiry"]) == selected_expiry]
    strikes = sorted({float(r["strike"]) for r in selected})
    atm = min(strikes, key=lambda strike: abs(strike - spot))
    index = strikes.index(atm)
    window = set(strikes[max(0, index - strikes_per_side):index + strikes_per_side + 1])
    out = [
        Instrument(
            tradingsymbol=r["tradingsymbol"],
            instrument_token=int(r["instrument_token"]),
            underlying=underlying,
            expiry=selected_expiry,
            strike=float(r["strike"]),
            option_type=OptionType(r["instrument_type"]),
            lot_size=int(r["lot_size"]),
        ) for r in selected if float(r["strike"]) in window
    ]
    return selected_expiry, out


def build_snapshot(
    underlying: str,
    spot: float,
    expiry: date,
    instruments: list[Instrument],
    ticks: dict[int, dict[str, Any]],
    now: datetime | None = None,
    acquisition_id: str | None = None,
) -> ChainSnapshot:
    now = now or datetime.now(UTC)
    quotes = []
    for instrument in instruments:
        tick = ticks.get(instrument.instrument_token, {})
        quotes.append(OptionQuote(
            instrument_token=instrument.instrument_token,
            instrument=instrument,
            ltp=tick.get("ltp"),
            bid=tick.get("bid"),
            ask=tick.get("ask"),
            volume=tick.get("volume"),
            oi=tick.get("oi"),
            exchange_ts=tick.get("exchange_ts"),
            trade_ts=tick.get("trade_ts"),
            received_at=tick.get("received_at", now),
        ))
    return ChainSnapshot(
        underlying=underlying,
        spot=spot,
        expiry=expiry,
        quotes=quotes,
        ts=now,
        acquisition_id=acquisition_id,
    )


def discover_chain_multi_expiry(
    instruments: Iterable[dict[str, Any]],
    underlying: str,
    spot: float,
    expiries_requested: int,
    strikes_per_side: int = 10,
    *,
    as_of: date | None = None,
) -> list[tuple[date, list[Instrument]]]:
    """Existing fixed-count API; horizon capture uses the separate API below."""
    today = as_of if as_of is not None else datetime.now(IST).date()
    rows = [row for row in instruments
            if row.get("name") == underlying and row.get("instrument_type") in {CE, PE}]
    if not rows:
        raise ValueError(f"No NFO options for {underlying}")
    if isinstance(expiries_requested, bool) or not isinstance(expiries_requested, int) or expiries_requested < 1:
        raise ValueError("expiries_requested must be a positive integer")
    expiries = sorted({_as_date(row["expiry"]) for row in rows
                       if _as_date(row["expiry"]) >= today})
    if len(expiries) < expiries_requested:
        raise ValueError(f"Requested {expiries_requested} expiries, but only {len(expiries)} are available")
    return [discover_chain(rows, underlying, spot, expiry, strikes_per_side, as_of=today)
            for expiry in expiries[:expiries_requested]]


def discover_chain_for_horizon(
    instruments: Iterable[dict[str, Any]], underlying: str, spot: float, *,
    as_of: date, horizon_days: int = 90, strikes_per_side: int = 10,
) -> list[tuple[date, list[Instrument]]]:
    """Build expiry-isolated chains through the first listing beyond horizon.

    Explicit as_of avoids wall-clock dependence during replay. This API does
    not activate horizon capture in providers still using the fixed-count API.
    """
    rows = [row for row in instruments
            if row.get("name") == underlying and row.get("instrument_type") in {CE, PE}]
    if not rows:
        raise ValueError(f"No NFO options for {underlying}")
    expiries = select_capture_expiries(
        (_as_date(row["expiry"]) for row in rows), as_of=as_of, horizon_days=horizon_days
    )
    return [discover_chain(rows, underlying, spot, expiry, strikes_per_side, as_of=as_of)
            for expiry in expiries]
