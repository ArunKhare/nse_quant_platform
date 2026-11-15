"""Corporate-actions and earnings calendar; research-only registry, no execution authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class CorporateAction:
    symbol: str
    action_type: str  # DIVIDEND, SPLIT, BONUS, BUYBACK
    ex_date: date
    record_date: date | None
    details: str | None = None
    decision_eligibility_asserted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "action_type": self.action_type,
            "ex_date": self.ex_date.isoformat(),
            "record_date": self.record_date.isoformat() if self.record_date else None,
            "details": self.details,
            "decision_eligibility_asserted": self.decision_eligibility_asserted,
        }


@dataclass(frozen=True)
class EarningsEvent:
    symbol: str
    earnings_date: date
    quarter: str | None = None
    consensus_eps: float | None = None
    decision_eligibility_asserted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "earnings_date": self.earnings_date.isoformat(),
            "quarter": self.quarter,
            "consensus_eps": self.consensus_eps,
            "decision_eligibility_asserted": self.decision_eligibility_asserted,
        }


@dataclass(frozen=True)
class CalendarSettings:
    earnings_blackout_days_before: int = 2
    earnings_blackout_days_after: int = 1
    corporate_action_blackout_days: int = 1


def is_earnings_blackout(
    *,
    as_of: date,
    earnings: list[EarningsEvent],
    settings: CalendarSettings | None = None,
) -> bool:
    """Return True if as_of falls within any earnings blackout window."""
    settings = settings or CalendarSettings()
    for event in earnings:
        if event.symbol and as_of >= event.earnings_date and as_of <= event.earnings_date:
            return True
        before_start = event.earnings_date.toordinal() - settings.earnings_blackout_days_before
        after_end = event.earnings_date.toordinal() + settings.earnings_blackout_days_after
        if before_start <= as_of.toordinal() <= after_end:
            return True
    return False


def is_corporate_action_blackout(
    *,
    as_of: date,
    actions: list[CorporateAction],
    settings: CalendarSettings | None = None,
) -> bool:
    """Return True if as_of falls within any corporate-action blackout window."""
    settings = settings or CalendarSettings()
    for action in actions:
        start = action.ex_date.toordinal() - settings.corporate_action_blackout_days
        end = action.ex_date.toordinal() + settings.corporate_action_blackout_days
        if start <= as_of.toordinal() <= end:
            return True
    return False


def upcoming_earnings(
    *,
    as_of: date,
    earnings: list[EarningsEvent],
    days_ahead: int = 30,
) -> list[EarningsEvent]:
    """Return earnings events within the next days_ahead days."""
    end = as_of.toordinal() + days_ahead
    return sorted(
        (e for e in earnings if as_of.toordinal() <= e.earnings_date.toordinal() <= end),
        key=lambda e: e.earnings_date,
    )


def upcoming_corporate_actions(
    *,
    as_of: date,
    actions: list[CorporateAction],
    days_ahead: int = 30,
) -> list[CorporateAction]:
    """Return corporate actions within the next days_ahead days."""
    end = as_of.toordinal() + days_ahead
    return sorted(
        (a for a in actions if as_of.toordinal() <= a.ex_date.toordinal() <= end),
        key=lambda a: a.ex_date,
    )


def build_calendar_summary(
    *,
    as_of: date,
    earnings: list[EarningsEvent],
    actions: list[CorporateAction],
    settings: CalendarSettings | None = None,
) -> dict[str, Any]:
    """Build a calendar summary payload; observational only."""
    settings = settings or CalendarSettings()
    return {
        "as_of": as_of.isoformat(),
        "earnings_blackout": is_earnings_blackout(as_of=as_of, earnings=earnings, settings=settings),
        "corporate_action_blackout": is_corporate_action_blackout(as_of=as_of, actions=actions, settings=settings),
        "upcoming_earnings": [e.to_dict() for e in upcoming_earnings(as_of=as_of, earnings=earnings)],
        "upcoming_corporate_actions": [a.to_dict() for a in upcoming_corporate_actions(as_of=as_of, actions=actions)],
        "decision_eligibility_asserted": False,
    }
