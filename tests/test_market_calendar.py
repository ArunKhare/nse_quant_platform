from datetime import date

from nse_quant.core.market_calendar import is_nse_trading_day


def test_nse_holiday_is_closed():
    assert not is_nse_trading_day(date(2026, 10, 20))


def test_weekday_is_open():
    assert is_nse_trading_day(date(2026, 10, 19))


def test_weekend_is_closed():
    assert not is_nse_trading_day(date(2026, 10, 17))
