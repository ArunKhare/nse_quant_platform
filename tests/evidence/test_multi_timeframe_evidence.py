from datetime import datetime

from nse_quant.research.candle_resampler import (
    latest_completed_candles,
)


def make_candle(minute: int, close: float) -> dict:
    return {
        "date": datetime(2026, 10, 22, 9, minute),
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": 100,
    }


def test_fifteen_minute_bucket_requires_complete_candles():
    candles = [make_candle(minute, 100 + minute) for minute in range(15)]

    completed = latest_completed_candles(
        candles,
        interval_minutes=15,
        limit=10,
    )

    assert completed == []


def test_completed_fifteen_minute_bucket_is_resampled():
    candles = []

    for minute in range(16):
        candles.append(make_candle(minute, 100 + minute))

    completed = latest_completed_candles(
        candles,
        interval_minutes=15,
        limit=10,
    )

    assert len(completed) == 1
    assert completed[0].open == 100
    assert completed[0].close == 114
    assert completed[0].high == 115
    assert completed[0].low == 99
    assert completed[0].candle_count == 15