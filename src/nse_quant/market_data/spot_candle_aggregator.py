"""Aggregate live spot ticks into 1-minute OHLCV candles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class SpotCandle:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    oi: int | None


class SpotCandleAggregator:
    def __init__(self) -> None:
        self._current_minute: datetime | None = None
        self._open: float | None = None
        self._high: float | None = None
        self._low: float | None = None
        self._close: float | None = None
        self._volume = 0
        self._oi: int | None = None

    def add_tick(
        self,
        *,
        ts: datetime,
        price: float | None,
        volume: int | None,
        oi: int | None = None,
    ) -> SpotCandle | None:
        if price is None or price <= 0:
            return None

        minute = ts.replace(second=0, microsecond=0)

        if self._current_minute is None:
            self._start_new(minute, price, volume, oi)
            return None

        if minute > self._current_minute:
            completed = self._complete()
            self._start_new(minute, price, volume, oi)
            return completed

        self._high = max(self._high or price, price)
        self._low = min(self._low or price, price)
        self._close = price
        self._volume += volume or 0
        self._oi = oi if oi is not None else self._oi
        return None

    def _start_new(
        self,
        minute: datetime,
        price: float,
        volume: int | None,
        oi: int | None,
    ) -> None:
        self._current_minute = minute
        self._open = price
        self._high = price
        self._low = price
        self._close = price
        self._volume = volume or 0
        self._oi = oi

    def _complete(self) -> SpotCandle:
        assert self._current_minute is not None
        assert self._open is not None
        assert self._high is not None
        assert self._low is not None
        assert self._close is not None

        return SpotCandle(
            ts=self._current_minute,
            open=self._open,
            high=self._high,
            low=self._low,
            close=self._close,
            volume=self._volume,
            oi=self._oi,
        )

    def flush(self) -> SpotCandle | None:
        if self._current_minute is None:
            return None
        return self._complete()
