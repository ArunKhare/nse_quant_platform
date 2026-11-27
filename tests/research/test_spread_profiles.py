"""Tests for NIFTY directional defined-risk spread profiles."""

from __future__ import annotations

from nse_quant.research.spread_profiles import (
    PROFILES,
    all_profiles_summary,
    get_profile,
    list_directions,
    list_horizons,
    list_profiles,
    profile_summary,
)


def test_all_profiles_present():
    assert len(PROFILES) == 6
    ids = {p.profile_id for p in PROFILES}
    assert {
        "nifty_intraday_bull_call_spread",
        "nifty_swing_bull_call_spread",
        "nifty_positional_bull_call_spread",
        "nifty_intraday_bear_put_spread",
        "nifty_swing_bear_put_spread",
        "nifty_positional_bear_put_spread",
    } == ids


def test_get_profile_roundtrip():
    profile = get_profile("nifty_intraday_bull_call_spread")
    assert profile is not None
    assert profile.horizon == "intraday"
    assert profile.direction == "BULLISH"
    assert profile.underlying == "NIFTY"
    assert profile.decision_eligibility_asserted is False
    assert get_profile("nonexistent") is None


def test_list_profiles_filters():
    bullish = list_profiles(direction="BULLISH")
    assert len(bullish) == 3
    bearish = list_profiles(direction="BEARISH")
    assert len(bearish) == 3
    intraday = list_profiles(horizon="intraday")
    assert len(intraday) == 2
    nifty = list_profiles(underlying="NIFTY")
    assert len(nifty) == 6
    both = list_profiles(horizon="swing", direction="BULLISH")
    assert len(both) == 1


def test_list_horizons_and_directions():
    assert list_horizons() == ["intraday", "positional", "swing"]
    assert list_directions() == ["BEARISH", "BULLISH"]


def test_profile_summary_shape():
    profile = get_profile("nifty_swing_bear_put_spread")
    summary = profile_summary(profile)
    assert summary["profile_id"] == "nifty_swing_bear_put_spread"
    assert summary["direction"] == "BEARISH"
    assert summary["decision_eligibility_asserted"] is False
    assert "market_tags" in summary


def test_all_profiles_summary_shape():
    summaries = all_profiles_summary()
    assert len(summaries) == 6
    for item in summaries:
        assert item["decision_eligibility_asserted"] is False
        assert "profile_id" in item and "direction" in item
