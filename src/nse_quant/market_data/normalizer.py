"""Kite tick normalization."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..core.models import Quote


def normalize_tick(tick: dict[str, Any], received_at: datetime | None = None) -> Quote:
    received_at = received_at or datetime.now(UTC)
    depth = tick.get("depth") or {}
    buy = (depth.get("buy") or [{}])[0]
    sell = (depth.get("sell") or [{}])[0]
    return Quote(
        instrument_token=int(tick["instrument_token"]),
        ltp=tick.get("last_price"),
        bid=buy.get("price"),
        ask=sell.get("price"),
        volume=tick.get("volume"),
        oi=tick.get("oi"),
        exchange_ts=tick.get("exchange_timestamp")
        if isinstance(tick.get("exchange_timestamp"), datetime)
        else None,
        trade_ts=tick.get("last_trade_time")
        if isinstance(tick.get("last_trade_time"), datetime)
        else None,
        received_at=received_at,
    )


def is_fresh(q: Quote, now: datetime, stale_seconds: float) -> bool:
    ref = q.exchange_ts or q.trade_ts or q.received_at
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return abs((now - ref).total_seconds()) <= stale_seconds
