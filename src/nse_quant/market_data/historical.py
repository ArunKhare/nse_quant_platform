"""Helpers for selecting historical candle request ranges."""

from __future__ import annotations

from datetime import datetime, timedelta

HISTORICAL_LOOKBACK_DAYS = {
    "1m": 5,
    "15m": 30,
    "60m": 90,
    "day": 365 * 3,
}


def get_historical_date_range(
    interval: str,
    end_dt: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Return the default date range for a historical candle interval."""
    to_dt = end_dt or datetime.now()
    lookback_days = HISTORICAL_LOOKBACK_DAYS.get(interval, 30)
    return to_dt - timedelta(days=lookback_days), to_dt
