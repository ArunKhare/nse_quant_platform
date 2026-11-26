from __future__ import annotations

from datetime import date, timedelta

import pytest

from nse_quant.research.institutional_regime_price_action_v5 import (
    PRICE_ACTION_CLASSIFIER_VERSION,
    DailyBar,
    InstitutionalRegimePriceActionSettings,
    classify_daily_price_action,
)


def trading_dates(count: int) -> list[date]:
    result: list[date] = []
    current = date(2025, 1, 1)
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current)
        current += timedelta(days=1)
    return result


def trending_bars(direction: int, count: int = 280) -> list[DailyBar]:
    dates = trading_dates(count)
    bars: list[DailyBar] = []
    previous = 100.0
    for index, trade_date in enumerate(dates):
        close = 100.0 + direction * index * 0.5
        opening = previous
        bars.append(
            DailyBar(
                trade_date=trade_date,
                open=opening,
                high=max(opening, close) + 1.0,
                low=min(opening, close) - 1.0,
                close=close,
                volume=100_000.0,
            )
        )
        previous = close
    return bars


def test_completed_daily_bars_produce_canonical_bull_trend() -> None:
    result = classify_daily_price_action(
        trending_bars(1),
        InstitutionalRegimePriceActionSettings(),
    )

    assert result["available"] is True
    assert result["complete"] is True
    assert result["state"] == "STRONG_BULL_TREND"
    assert result["classifier_version"] == PRICE_ACTION_CLASSIFIER_VERSION
    assert result["persistence_closes"] == 2
    assert result["decision_eligibility_asserted"] is False
    assert result["diagnostics"]["adx14"] >= 25.0
    assert result["diagnostics"]["er20"] >= 0.35


def test_completed_daily_bars_produce_canonical_bear_trend() -> None:
    result = classify_daily_price_action(
        trending_bars(-1),
        InstitutionalRegimePriceActionSettings(),
    )

    assert result["complete"] is True
    assert result["state"] == "STRONG_BEAR_TREND"


def test_history_floor_accounts_for_252_atr_observations_and_persistence() -> None:
    result = classify_daily_price_action(
        trending_bars(1, count=266),
        InstitutionalRegimePriceActionSettings(),
    )

    assert result["available"] is False
    assert result["reason"] == "insufficient_daily_history"
    assert result["minimum_daily_bars"] == 267


def test_confidence_floor_fails_closed() -> None:
    result = classify_daily_price_action(
        trending_bars(1),
        InstitutionalRegimePriceActionSettings(confidence_floor=0.99),
    )

    assert result["available"] is False
    assert result["reason"] == "no_state_confirmed_for_two_consecutive_closes"


def test_duplicate_or_unordered_daily_dates_are_rejected() -> None:
    bars = trending_bars(1)
    bars[10] = bars[9]

    result = classify_daily_price_action(
        bars,
        InstitutionalRegimePriceActionSettings(),
    )

    assert result["available"] is False
    assert result["reason"] == "daily_bars_not_strictly_ordered_unique"


def test_invalid_ohlc_is_rejected() -> None:
    bars = trending_bars(1)
    last = bars[-1]
    bars[-1] = DailyBar(
        trade_date=last.trade_date,
        open=last.open,
        high=last.close - 1.0,
        low=last.low,
        close=last.close,
        volume=last.volume,
    )

    result = classify_daily_price_action(
        bars,
        InstitutionalRegimePriceActionSettings(),
    )

    assert result["available"] is False
    assert result["reason"] == "invalid_daily_ohlc"


def test_settings_reject_history_limit_below_required_minimum() -> None:
    with pytest.raises(ValueError):
        InstitutionalRegimePriceActionSettings(
            daily_history_limit=267,
            minimum_daily_bars=268,
        )
