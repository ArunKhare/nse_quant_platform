"""Resample completed 1-minute candles into higher-timeframe buckets."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ResampledCandle:
    bucket_start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    candle_count: int


def _bucket_start(ts: datetime, minutes: int) -> datetime:
    minute_of_day = ts.hour * 60 + ts.minute
    aligned_minute = (minute_of_day // minutes) * minutes

    return ts.replace(
        hour=aligned_minute // 60,
        minute=aligned_minute % 60,
        second=0,
        microsecond=0,
    )


def resample_candles(
    candles: list[dict[str, Any]],
    *,
    interval_minutes: int,
) -> list[ResampledCandle]:
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be positive")

    grouped: dict[datetime, list[dict[str, Any]]] = defaultdict(list)

    for candle in candles:
        ts = candle["date"]

        if ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)

        grouped[_bucket_start(ts, interval_minutes)].append(candle)

    resampled: list[ResampledCandle] = []

    for bucket_start in sorted(grouped):
        rows = grouped[bucket_start]
        rows = sorted(rows, key=lambda row: row["date"])

        resampled.append(
            ResampledCandle(
                bucket_start=bucket_start,
                open=float(rows[0]["open"]),
                high=float(max(row["high"] for row in rows)),
                low=float(min(row["low"] for row in rows)),
                close=float(rows[-1]["close"]),
                volume=float(sum(row.get("volume") or 0 for row in rows)),
                candle_count=len(rows),
            )
        )

    return resampled


def latest_completed_candles(
    candles: list[dict[str, Any]],
    *,
    interval_minutes: int,
    limit: int,
) -> list[ResampledCandle]:
    """Return only fully populated buckets, excluding the active bucket."""

    if not candles:
        return []

    sorted_candles = sorted(candles, key=lambda row: row["date"])
    latest_ts = sorted_candles[-1]["date"]

    if latest_ts.tzinfo is not None:
        latest_ts = latest_ts.replace(tzinfo=None)

    active_bucket = _bucket_start(latest_ts, interval_minutes)

    completed = [
        candle
        for candle in resample_candles(
            sorted_candles,
            interval_minutes=interval_minutes,
        )
        if candle.bucket_start < active_bucket
        and candle.candle_count == interval_minutes
    ]

    return completed[-limit:]