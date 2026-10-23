from datetime import date, datetime, time

import pytest

from nse_quant.core.trading_calendar import (
    IST,
    NSETradingCalendar,
    SpecialSession,
)


def test_weekend_is_closed() -> None:
    calendar = NSETradingCalendar()

    assert calendar.is_trading_day(date(2026, 10, 17)) is False
    assert calendar.is_trading_day(date(2026, 10, 18)) is False


def test_configured_holiday_is_closed() -> None:
    holiday = date(2026, 10, 20)
    calendar = NSETradingCalendar(closed_dates={holiday})

    assert calendar.is_trading_day(holiday) is False


def test_regular_session_bounds() -> None:
    calendar = NSETradingCalendar()
    session = calendar.session_for_date(date(2026, 10, 19))

    assert session is not None
    assert session.open_time == time(9, 15)
    assert session.close_time == time(15, 30)


def test_sessions_between_excludes_weekends_and_holidays() -> None:
    calendar = NSETradingCalendar(
        closed_dates={date(2026, 10, 20)},
    )

    sessions = calendar.sessions_between(
        date(2026, 10, 19),
        date(2026, 10, 23),
    )

    assert [session.session_date for session in sessions] == [
        date(2026, 10, 19),
        date(2026, 10, 21),
        date(2026, 10, 22),
        date(2026, 10, 23),
    ]


def test_special_session_excluded_by_default() -> None:
    special_day = date(2026, 10, 24)
    calendar = NSETradingCalendar(
        special_sessions=[
            SpecialSession(
                session_date=special_day,
                open_time=time(9, 0),
                close_time=time(10, 0),
                session_type="SPECIAL",
            )
        ]
    )

    assert calendar.is_trading_day(special_day) is False
    assert (
        calendar.is_trading_day(
            special_day,
            include_special=True,
        )
        is True
    )
    assert calendar.session_for_date(special_day) is None


def test_market_open_requires_regular_session() -> None:
    calendar = NSETradingCalendar()

    open_ts = datetime(2026, 10, 19, 10, 0, tzinfo=IST)
    before_open = datetime(2026, 10, 19, 9, 14, tzinfo=IST)
    after_close = datetime(2026, 10, 19, 15, 30, tzinfo=IST)

    assert calendar.is_market_open(open_ts) is True
    assert calendar.is_market_open(before_open) is False
    assert calendar.is_market_open(after_close) is False


def test_naive_timestamp_is_rejected() -> None:
    calendar = NSETradingCalendar()

    with pytest.raises(ValueError):
        calendar.is_market_open(datetime(2026, 10, 19, 10, 0))
