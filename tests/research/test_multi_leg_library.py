"""Tests for the multi-leg NIFTY strategy library."""

from __future__ import annotations

from nse_quant.research.multi_leg_library import (
    PROFILES,
    all_profiles_summary,
    get_profile,
    list_horizons,
    list_profiles,
    list_structures,
    profile_summary,
)


def test_all_profiles_present():
    assert len(PROFILES) == 6
    ids = {p.profile_id for p in PROFILES}
    assert {
        "nifty_intraday_iron_fly",
        "nifty_swing_iron_fly",
        "nifty_positional_iron_fly",
        "nifty_swing_calendar_spread",
        "nifty_positional_calendar_spread",
        "nifty_swing_ratio_spread",
    } == ids


def test_get_profile_roundtrip():
    profile = get_profile("nifty_intraday_iron_fly")
    assert profile is not None
    assert profile.horizon == "intraday"
    assert profile.structure == "iron_fly"
    assert profile.underlying == "NIFTY"
    assert profile.decision_eligibility_asserted is False
    assert len(profile.legs) == 4
    assert get_profile("nonexistent") is None


def test_list_profiles_filters():
    iron_fly = list_profiles(structure="iron_fly")
    assert len(iron_fly) == 3
    calendar = list_profiles(structure="calendar_spread")
    assert len(calendar) == 2
    ratio = list_profiles(structure="ratio_spread")
    assert len(ratio) == 1
    intraday = list_profiles(horizon="intraday")
    assert len(intraday) == 1
    nifty = list_profiles(underlying="NIFTY")
    assert len(nifty) == 6
    both = list_profiles(horizon="swing", structure="iron_fly")
    assert len(both) == 1


def test_list_horizons_and_structures():
    assert list_horizons() == ["intraday", "positional", "swing"]
    assert list_structures() == ["calendar_spread", "iron_fly", "ratio_spread"]


def test_profile_summary_shape():
    profile = get_profile("nifty_swing_calendar_spread")
    summary = profile_summary(profile)
    assert summary["profile_id"] == "nifty_swing_calendar_spread"
    assert summary["structure"] == "calendar_spread"
    assert summary["decision_eligibility_asserted"] is False
    assert summary["legs"] == ["long_near_expiry", "short_far_expiry"]


def test_all_profiles_summary_shape():
    summaries = all_profiles_summary()
    assert len(summaries) == 6
    for item in summaries:
        assert item["decision_eligibility_asserted"] is False
        assert "profile_id" in item and "structure" in item and "legs" in item
