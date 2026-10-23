"""Configurable NSE equity trading-session calendar."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from nse_quant.core.constants import IST, REGULAR_SESSION_CLOSE, REGULAR_SESSION_OPEN


@dataclass(frozen=True)
class TradingSession:
    """A single NSE trading session in Asia/Kolkata."""

    session_date: date
    open_time: time
    close_time: time
    session_type: str = "REGULAR"

    @property
    def opens_at(self) -> datetime:
        return datetime.combine(
            self.session_date,
            self.open_time,
            tzinfo=IST,
        )

    @property
    def closes_at(self) -> datetime:
        return datetime.combine(
            self.session_date,
            self.close_time,
            tzinfo=IST,
        )

    def contains(self, timestamp: datetime) -> bool:
        """Return whether an aware timestamp falls within the session."""
        if timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")

        local_ts = timestamp.astimezone(IST)
        return self.opens_at <= local_ts < self.closes_at


@dataclass(frozen=True)
class SpecialSession:
    """An exchange-declared special, pre-open, or DR session."""

    session_date: date
    open_time: time
    close_time: time
    session_type: str


class NSETradingCalendar:
    """Minimal configurable calendar for NSE equity sessions.

    Regular sessions run 09:15-15:30 IST on weekdays. Holidays and special
    sessions are supplied by configuration rather than hardcoded multi-year
    Python lists.
    """

    def __init__(
        self,
        *,
        closed_dates: set[date] | None = None,
        special_sessions: list[SpecialSession] | None = None,
    ) -> None:
        self.closed_dates = set(closed_dates or set())
        self._special_sessions: dict[date, list[SpecialSession]] = {}

        for session in special_sessions or []:
            self._special_sessions.setdefault(
                session.session_date,
                [],
            ).append(session)

    def is_trading_day(
        self,
        day: date,
        *,
        include_special: bool = False,
    ) -> bool:
        if day in self.closed_dates:
            return False

        if include_special and day in self._special_sessions:
            return True

        return day.weekday() < 5

    def session_for_date(
        self,
        day: date,
        *,
        include_special: bool = False,
    ) -> TradingSession | None:
        if not self.is_trading_day(
            day,
            include_special=include_special,
        ):
            return None

        return TradingSession(
            session_date=day,
            open_time=REGULAR_SESSION_OPEN,
            close_time=REGULAR_SESSION_CLOSE,
        )

    def sessions_between(
        self,
        start_date: date,
        end_date: date,
        *,
        include_special: bool = False,
    ) -> list[TradingSession]:
        """Return regular sessions in the inclusive date range.

        Special sessions are excluded by default so technical feature windows
        remain based on the standard continuous equity session.
        """
        if end_date < start_date:
            raise ValueError("end_date must not precede start_date")

        sessions: list[TradingSession] = []

        current = start_date
        while current <= end_date:
            session = self.session_for_date(
                current,
                include_special=include_special,
            )
            if session is not None:
                sessions.append(session)
            current = date.fromordinal(current.toordinal() + 1)

        return sessions

    def special_sessions_for_date(self, day: date) -> list[SpecialSession]:
        return list(self._special_sessions.get(day, []))

    def is_market_open(self, timestamp: datetime) -> bool:
        """Return whether the timestamp is inside a regular session."""
        if timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")

        local_ts = timestamp.astimezone(IST)
        session = self.session_for_date(local_ts.date())
        return session is not None and session.contains(local_ts)
