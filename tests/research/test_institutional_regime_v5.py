from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from nse_quant.core.regime_registry import IvState, Skew, is_canonical_regime_label
from nse_quant.research.institutional_regime_v5 import DailyValue, PriceDiagnostics, classify


def inputs() -> dict:
    first = date(2025, 1, 1)
    sessions = [first + timedelta(days=i) for i in range(180)
                if (first + timedelta(days=i)).weekday() < 5][:120]
    ivs = tuple(DailyValue(day, 0.10 + i * 0.001, "india_vix_eod")
                for i, day in enumerate(sessions))
    rrs = tuple(DailyValue(day, -0.05 + i * 0.0002, "surface_rr25")
                for i, day in enumerate(sessions))
    previous = PriceDiagnostics(date(2026, 11, 19), 15, 0.1, 70, 85, 50, 0.7, 1, 1, 1)
    return dict(
        as_of=datetime(2026, 11, 23, 5, tzinfo=UTC),
        surface_time=datetime(2026, 11, 23, 5, tzinfo=UTC),
        iv30=0.23, iv90=0.25, iv30_source="internal_cm",
        eod_iv_close=DailyValue(date(2026, 11, 20), 0.23, "india_vix_eod"), eod_iv_history=ivs,
        rr25=-0.03, rr25_source="surface_rr25",
        rr25_history=rrs, previous_close=previous,
        latest_close=replace(previous, session=date(2026, 11, 20)),
    )


def test_complete_label_is_canonical_and_observation_only() -> None:
    result = classify(**inputs())
    assert result["regime_label"] == "HIGH_IV_CONTANGO_NORMAL_SKEW_HIGH_VOL_CHOP"
    assert is_canonical_regime_label(result["regime_label"])
    assert result["complete"]
    assert result["mode"] == "observation"
    assert result["decision_eligibility_asserted"] is False
    assert result["thresholds_provisional"] is True


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"adx14": 40, "er20": 0.6}, "STRONG_BULL_TREND"),
        ({"adx14": 40, "er20": 0.6, "change20": -1, "sma20_slope": -1,
          "di_difference": -1}, "STRONG_BEAR_TREND"),
        ({"atr_percentile": 20, "bandwidth_percentile": 5}, "COMPRESSION"),
        ({"atr_percentile": 50, "range_position": 0.8}, "RANGE_HIGH"),
        ({"atr_percentile": 50, "range_position": 0.2}, "RANGE_LOW"),
        ({}, "HIGH_VOL_CHOP"),
    ],
)
def test_six_price_action_states(changes: dict, expected: str) -> None:
    kwargs = inputs()
    for key in ("previous_close", "latest_close"):
        kwargs[key] = replace(kwargs[key], **changes)
    result = classify(**kwargs)
    assert result["complete"], result
    assert result["regime_components"]["price_action"] == expected
    assert is_canonical_regime_label(result["regime_label"])


@pytest.mark.parametrize(
    "change",
    [
        {"eod_iv_history": ()}, {"rr25_history": ()},
        {"iv30_source": "india_vix"}, {"eod_iv_close": DailyValue(date(2026, 11, 20), float("nan"), "india_vix_eod")},
        {"iv90": 0}, {"previous_iv_state": "NORMAL_IV"},
        {"previous_skew": "HIGH_CALL_SKEW"}, {"minimum_confidence": 1.1},
        {"surface_time": datetime(2026, 11, 23, 6, tzinfo=UTC)},
        {"surface_time": datetime(2026, 11, 23, 4, tzinfo=UTC)},
    ],
)
def test_invalid_or_unavailable_inputs_never_produce_label(change: dict) -> None:
    result = classify(**(inputs() | change))
    assert result["regime_label"] is None
    assert not result["complete"]
    assert result["reason"]


def test_partial_session_and_unconfirmed_transition_are_rejected() -> None:
    kwargs = inputs()
    kwargs["latest_close"] = replace(kwargs["latest_close"], session=date(2026, 11, 23))
    assert classify(**kwargs)["reason"] == "completed_ordered_daily_features_required"
    kwargs = inputs()
    kwargs["latest_close"] = replace(kwargs["latest_close"], atr_percentile=20, bandwidth_percentile=5)
    assert classify(**kwargs)["reason"] == "price_action_awaiting_second_close"


def test_history_source_mixing_and_duplicate_days_are_rejected() -> None:
    kwargs = inputs()
    history = kwargs["eod_iv_history"]
    kwargs["eod_iv_history"] = history[:-1] + (replace(history[-1], source="live_india_vix"),)
    assert not classify(**kwargs)["complete"]
    kwargs["eod_iv_history"] = history + (history[-1],)
    assert not classify(**kwargs)["complete"]


def test_classifier_uses_canonical_inclusive_current_ivr_window() -> None:
    kwargs = inputs()
    kwargs["eod_iv_close"] = replace(kwargs["eod_iv_close"], value=0.16)
    result = classify(**kwargs)
    assert result["complete"], result
    assert result["diagnostics"]["ivp"] == pytest.approx(50.0)
    assert result["diagnostics"]["ivr"] == pytest.approx(50.0)


def test_iv_and_skew_hysteresis() -> None:
    kwargs = inputs()
    kwargs["eod_iv_close"] = replace(kwargs["eod_iv_close"], value=0.178)
    assert classify(**kwargs)["regime_components"]["iv_state"] == "LOW_IV"
    kwargs["previous_iv_state"] = IvState.HIGH_IV
    assert classify(**kwargs)["regime_components"]["iv_state"] == "HIGH_IV"
    kwargs["rr25"] = -0.04
    assert classify(**kwargs)["regime_components"]["skew"] == "NORMAL_SKEW"
    kwargs["previous_skew"] = Skew.HIGH_PUT_SKEW
    assert classify(**kwargs)["regime_components"]["skew"] == "HIGH_PUT_SKEW"



def test_eod_iv30_requires_recent_completed_close_and_rejects_live_series() -> None:
    kwargs = inputs()
    kwargs["eod_iv_close"] = replace(kwargs["eod_iv_close"], session=date(2026, 11, 23))
    assert classify(**kwargs)["reason"] == "completed_recent_eod_iv30_required"
    kwargs = inputs()
    kwargs["eod_iv_close"] = replace(kwargs["eod_iv_close"], session=date(2026, 11, 18))
    assert classify(**kwargs)["reason"] == "completed_recent_eod_iv30_required"
    kwargs = inputs()
    kwargs["eod_iv_close"] = replace(kwargs["eod_iv_close"], source="india_vix_live")
    assert classify(**kwargs)["reason"] == "completed_recent_eod_iv30_required"
