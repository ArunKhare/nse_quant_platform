"""Tests for multi-horizon NIFTY strategy profiles."""

from __future__ import annotations

from nse_quant.research.strategy_profiles import (
    PROFILES,
    all_profiles_summary,
    get_profile,
    list_horizons,
    list_profiles,
    profile_summary,
)


def test_all_profiles_present():
    assert len(PROFILES) == 6
    ids = {p.profile_id for p in PROFILES}
    assert {
        "nifty_intraday_iron_condor",
        "nifty_swing_iron_condor",
        "nifty_positional_butterfly",
        "nifty_intraday_butterfly",
        "nifty_swing_butterfly",
        "nifty_positional_iron_condor",
    } == ids


def test_get_profile_roundtrip():
    profile = get_profile("nifty_intraday_iron_condor")
    assert profile is not None
    assert profile.horizon == "intraday"
    assert profile.underlying == "NIFTY"
    assert profile.decision_eligibility_asserted is False
    assert get_profile("nonexistent") is None


def test_list_profiles_filters_by_horizon_and_underlying():
    intraday = list_profiles(horizon="intraday")
    assert len(intraday) == 2
    positional = list_profiles(horizon="positional")
    assert len(positional) == 2
    nifty = list_profiles(underlying="NIFTY")
    assert len(nifty) == 6
    both = list_profiles(horizon="swing", underlying="NIFTY")
    assert len(both) == 2


def test_list_horizons():
    assert list_horizons() == ["intraday", "positional", "swing"]


def test_profile_summary_shape():
    profile = get_profile("nifty_swing_butterfly")
    summary = profile_summary(profile)
    assert summary["profile_id"] == "nifty_swing_butterfly"
    assert summary["horizon"] == "swing"
    assert summary["decision_eligibility_asserted"] is False
    assert "allowed_regimes" in summary


def test_all_profiles_summary_shape():
    summaries = all_profiles_summary()
    assert len(summaries) == 6
    for item in summaries:
        assert item["decision_eligibility_asserted"] is False
        assert "profile_id" in item and "horizon" in item
