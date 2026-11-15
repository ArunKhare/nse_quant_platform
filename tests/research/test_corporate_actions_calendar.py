"""Tests for the corporate-actions and earnings calendar."""

from __future__ import annotations

from datetime import date

from nse_quant.research.corporate_actions_calendar import (
    CalendarSettings,
    CorporateAction,
    EarningsEvent,
    build_calendar_summary,
    is_corporate_action_blackout,
    is_earnings_blackout,
    upcoming_corporate_actions,
    upcoming_earnings,
)


def _earnings(day_offset: int, symbol: str = "RELIANCE"):
    return EarningsEvent(
        symbol=symbol,
        earnings_date=date(2026, 1, 15 + day_offset),
        quarter="Q3FY26",
        consensus_eps=25.0,
    )


def _action(day_offset: int, symbol: str = "RELIANCE", action_type: str = "DIVIDEND"):
    return CorporateAction(
        symbol=symbol,
        action_type=action_type,
        ex_date=date(2026, 2, 1 + day_offset),
        record_date=date(2026, 2, 2 + day_offset),
        details="synthetic",
    )


def test_is_earnings_blackout_inside_window():
    earnings = [_earnings(0)]
    assert is_earnings_blackout(as_of=date(2026, 1, 15), earnings=earnings) is True
    assert is_earnings_blackout(as_of=date(2026, 1, 14), earnings=earnings) is True
    assert is_earnings_blackout(as_of=date(2026, 1, 16), earnings=earnings) is True


def test_is_earnings_blackout_outside_window():
    earnings = [_earnings(0)]
    assert is_earnings_blackout(as_of=date(2026, 1, 10), earnings=earnings) is False
    assert is_earnings_blackout(as_of=date(2026, 1, 20), earnings=earnings) is False


def test_is_corporate_action_blackout_inside_window():
    actions = [_action(0)]
    assert is_corporate_action_blackout(as_of=date(2026, 2, 1), actions=actions) is True
    assert is_corporate_action_blackout(as_of=date(2026, 1, 31), actions=actions) is True
    assert is_corporate_action_blackout(as_of=date(2026, 2, 2), actions=actions) is True


def test_is_corporate_action_blackout_outside_window():
    actions = [_action(0)]
    assert is_corporate_action_blackout(as_of=date(2026, 1, 25), actions=actions) is False
    assert is_corporate_action_blackout(as_of=date(2026, 2, 10), actions=actions) is False


def test_upcoming_earnings_filters_and_sorts():
    earnings = [_earnings(10), _earnings(5), _earnings(40)]
    result = upcoming_earnings(as_of=date(2026, 1, 15), earnings=earnings, days_ahead=30)
    assert len(result) == 2
    assert result[0].earnings_date < result[1].earnings_date


def test_upcoming_corporate_actions_filters_and_sorts():
    actions = [_action(10), _action(5), _action(40)]
    result = upcoming_corporate_actions(as_of=date(2026, 2, 1), actions=actions, days_ahead=30)
    assert len(result) == 2
    assert result[0].ex_date < result[1].ex_date


def test_build_calendar_summary_shape():
    earnings = [_earnings(0)]
    actions = [_action(0)]
    summary = build_calendar_summary(as_of=date(2026, 1, 15), earnings=earnings, actions=actions)
    assert summary["decision_eligibility_asserted"] is False
    assert summary["earnings_blackout"] is True
    assert summary["corporate_action_blackout"] is False
    assert len(summary["upcoming_earnings"]) == 1
    assert len(summary["upcoming_corporate_actions"]) == 1


def test_settings_defaults():
    settings = CalendarSettings()
    assert settings.earnings_blackout_days_before == 2
    assert settings.earnings_blackout_days_after == 1
    assert settings.corporate_action_blackout_days == 1
