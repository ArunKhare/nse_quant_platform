"""Tests for market-session evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from nse_quant.research.market_session_evidence import (
    MarketSessionSettings,
    classify_market_session,
)


def _ist(hour: int, minute: int) -> datetime:
    return datetime(2026, 1, 5, hour, minute, tzinfo=UTC) - timedelta(hours=5, minutes=30)


def test_regular_session():
    settings = MarketSessionSettings(require_regular_session=True)
    result = classify_market_session(decision_ts=_ist(10, 0), settings=settings)
    assert result["available"] is True
    assert result["state"] == "REGULAR_SESSION"
    assert result["eligible_for_entry"] is True


def test_pre_market():
    settings = MarketSessionSettings(require_regular_session=True)
    result = classify_market_session(decision_ts=_ist(8, 0), settings=settings)
    assert result["state"] == "PRE_MARKET"
    assert result["eligible_for_entry"] is False


def test_post_market():
    settings = MarketSessionSettings(require_regular_session=True)
    result = classify_market_session(decision_ts=_ist(16, 0), settings=settings)
    assert result["state"] == "POST_MARKET"
    assert result["eligible_for_entry"] is False


def test_weekend_closed():
    settings = MarketSessionSettings(require_regular_session=True)
    saturday = datetime(2026, 1, 3, 10, 0, tzinfo=UTC)
    result = classify_market_session(decision_ts=saturday, settings=settings)
    assert result["state"] == "CLOSED"
    assert result["reason"] == "weekend"


def test_naive_timestamp_refused():
    settings = MarketSessionSettings()
    naive = datetime(2026, 1, 5, 10, 0)
    result = classify_market_session(decision_ts=naive, settings=settings)
    assert result["available"] is False
    assert result["reason"] == "aware_decision_timestamp_required"


def test_no_eligibility_assertion_when_not_required():
    settings = MarketSessionSettings(require_regular_session=False)
    result = classify_market_session(decision_ts=_ist(10, 0), settings=settings)
    assert result["eligible_for_entry"] is None
    assert result["decision_eligibility_asserted"] is False
