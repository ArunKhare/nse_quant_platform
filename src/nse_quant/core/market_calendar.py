"""NSE market calendar and trading-session utilities."""

from __future__ import annotations

from datetime import date, datetime

from nse_quant.core.constants import IST, MARKET_CLOSE, MARKET_OPEN

NSE_HOLIDAYS: dict[int, set[date]] = {
    2026: {
        date(2026, 1, 15),   # Municipal Corporation Elections, Maharashtra
        date(2026, 1, 26),   # Republic Day
        date(2026, 3, 3),    # Holi
        date(2026, 3, 26),   # Ram Navami
        date(2026, 3, 31),   # Mahavir Jayanti
        date(2026, 4, 3),    # Good Friday
        date(2026, 4, 14),   # Ambedkar Jayanti
        date(2026, 5, 1),    # Maharashtra Day
        date(2026, 5, 28),   # Bakri Id
        date(2026, 6, 26),   # Muharram
        date(2026, 9, 14),   # Ganesh Chaturthi
        date(2026, 10, 2),   # Gandhi Jayanti
        date(2026, 10, 20),  # Dussehra
        date(2026, 11, 10),  # Diwali-Balipratipada
        date(2026, 11, 24),  # Guru Nanak Dev Jayanti
        date(2026, 12, 25),  # Christmas
    },
}


def now_ist() -> datetime:
    return datetime.now(IST)


def is_nse_trading_day(day: date) -> bool:
    return (
        day.weekday() < 5
        and day not in NSE_HOLIDAYS.get(day.year, set())
    )


def is_market_open_now() -> bool:
    current = now_ist()
    return (
        is_nse_trading_day(current.date())
        and MARKET_OPEN <= current.time() < MARKET_CLOSE
    )


def is_market_closed_now() -> bool:
    return not is_market_open_now()