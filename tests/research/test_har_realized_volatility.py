from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta

import pytest

from nse_quant.core.constants import IST
from nse_quant.core.trading_calendar import NSETradingCalendar
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.har_realized_volatility import (
    HAR_RV_HORIZON_DAYS,
    HAR_RV_MEASURE,
    HAR_RV_METHOD,
    HAR_RV_VERSION,
    build_daily_rv_observations,
    calibrate_har_rv_forecast_errors,
    forecast_har_rv_30d,
)


def _session_candles(day: date, base: float) -> list[tuple[datetime, float, float]]:
    start = datetime.combine(day, time(9, 15), tzinfo=IST)
    rows = []
    for minute in range(375):
        price = base * (1.0 + minute * 0.00001)
        rows.append((start + timedelta(minutes=minute), price, price))
    return rows


def test_daily_rv_requires_complete_sessions_and_does_not_bridge_missing_day() -> None:
    days = [date(2026, 11, 23), date(2026, 11, 24), date(2026, 11, 25), date(2026, 11, 26)]
    candles = (
        _session_candles(days[0], 100.0)
        + _session_candles(days[1], 101.0)
        + _session_candles(days[2], 102.0)
        # Entire 26-Nov session intentionally absent.
    )
    result = build_daily_rv_observations(
        candles,
        calendar=NSETradingCalendar(),
        as_of=datetime(2026, 11, 26, 17, 0, tzinfo=IST),
    )
    assert [item.session_date for item in result] == days[1:3]
    assert all(item.source_minute_rows == 375 for item in result)
    assert result[0].overnight_return == pytest.approx(math.log(101.0 / (100.0 * (1 + 374 * 0.00001))))
    assert result[0].intraday_variance > 0
    assert result[0].realized_variance == pytest.approx(
        result[0].intraday_variance + result[0].overnight_return**2
    )


def test_daily_rv_rejects_incomplete_session_and_future_minutes() -> None:
    day1, day2 = date(2026, 11, 23), date(2026, 11, 24)
    candles = _session_candles(day1, 100.0) + _session_candles(day2, 101.0)[:-1]
    result = build_daily_rv_observations(
        candles,
        calendar=NSETradingCalendar(),
        as_of=datetime(2026, 11, 24, 15, 29, tzinfo=IST),
    )
    assert result == ()


def test_daily_rv_respects_configured_exchange_holidays() -> None:
    holiday = date(2026, 11, 24)
    candles = _session_candles(date(2026, 11, 23), 100.0) + _session_candles(
        date(2026, 11, 25), 102.0
    )
    result = build_daily_rv_observations(
        candles,
        calendar=NSETradingCalendar(closed_dates={holiday}),
        as_of=datetime(2026, 11, 25, 17, 0, tzinfo=IST),
    )
    assert [item.session_date for item in result] == [date(2026, 11, 25)]


def _synthetic_daily_variances(count: int) -> list[float]:
    return [
        0.0001 * (1.0 + 0.20 * math.sin(index / 7) + 0.10 * math.cos(index / 19) + index * 0.0001)
        for index in range(count)
    ]


def test_har_rv_forecasts_30_calendar_days_from_21_sessions() -> None:
    forecast, details = forecast_har_rv_30d(_synthetic_daily_variances(360))
    assert forecast is not None
    assert math.isfinite(forecast) and forecast > 0
    assert details["method"] == HAR_RV_METHOD
    assert details["version"] == HAR_RV_VERSION
    assert details["horizon_days"] == HAR_RV_HORIZON_DAYS
    assert details["horizon_sessions"] == 21
    assert details["measure"] == HAR_RV_MEASURE
    assert details["is_forecast"] is True
    assert details["gate_eligible"] is False
    assert details["diagnostic_only"] is True
    assert len(details["forecast_daily_variances"]) == 21


def test_har_rv_requires_full_training_window() -> None:
    forecast, details = forecast_har_rv_30d(_synthetic_daily_variances(273))
    assert forecast is None
    assert details["reason"] == "insufficient_har_rv_history"


def test_har_rv_walk_forward_calibration_produces_gate_margin() -> None:
    result = calibrate_har_rv_forecast_errors(_synthetic_daily_variances(360))
    assert result["samples"] >= 30
    assert result["reason"] is None
    assert result["absolute_error_p90"] >= 0
    assert result["mean_absolute_error"] >= 0
    assert result["gate_margin_eligible"] is True
    assert result["diagnostic_only"] is False


def test_har_rv_calibration_fails_closed_with_too_few_origins() -> None:
    result = calibrate_har_rv_forecast_errors(_synthetic_daily_variances(300))
    assert result["samples"] < 30
    assert result["absolute_error_p90"] is None
    assert result["gate_margin_eligible"] is False



def test_store_reader_returns_only_bounded_point_in_time_one_minute_candles(tmp_path) -> None:
    store = DuckDBStore(tmp_path / "har-rv.duckdb")
    try:
        base = datetime(2026, 11, 23, 9, 15, tzinfo=IST)
        store.write_spot_candles(
            candles=[
                {
                    "date": base,
                    "open": 100.0,
                    "high": 100.0,
                    "low": 100.0,
                    "close": 100.0,
                    "volume": 1,
                },
                {
                    "date": base + timedelta(minutes=1),
                    "open": 101.0,
                    "high": 101.0,
                    "low": 101.0,
                    "close": 101.0,
                    "volume": 1,
                },
                {
                    "date": base + timedelta(minutes=2),
                    "open": 102.0,
                    "high": 102.0,
                    "low": 102.0,
                    "close": 102.0,
                    "volume": 1,
                },
            ],
            symbol="NIFTY",
            instrument_token=256265,
            interval="1m",
        )
        rows = store.completed_one_minute_candles(
            instrument_token=256265,
            start=base,
            before=base + timedelta(minutes=2),
        )
        assert rows == [
            (base, 100.0, 100.0),
            (base + timedelta(minutes=1), 101.0, 101.0),
        ]
    finally:
        store.close()
