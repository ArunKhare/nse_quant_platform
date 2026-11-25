"""Pure feature tests; synthetic provenance is not native acquisition proof."""

import json
from copy import deepcopy
from datetime import date, datetime, timedelta

import pytest

from nse_quant.analytics import s2_iv30_features as api
from nse_quant.analytics import s2_iv30_history as history

AT = "2026-11-25T10:00:00+00:00"
DAY = "2026-11-24"


def provenance():
    return dict(
        observation_id="a" * 64,
        materialization_sha256="b" * 64,
        revision_id="c" * 64,
        materialization_available_at="2026-11-25T09:00:00+00:00",
    )


def eod_history(count=120, value=20.0):
    selected = date.fromisoformat(DAY)
    lines = ["date,close"]
    for index in range(count):
        lines.append(f"{selected - timedelta(days=count - index)},{10 + index / 100}")
    lines.append(f"{selected},{value}")
    raw = ("\n".join(lines) + "\n").encode()
    return history.build_history(
        raw_csv=raw,
        expected_raw_sha256=api.sha(raw),
        source_reference="synthetic-eod-file",
        received_at="2026-11-25T08:00:00+00:00",
        as_of=AT,
        date_column="date",
        close_column="close",
    )


def eod(count=120, **changes):
    raw = eod_history(count)
    args = dict(expected_history_sha256=api.sha(raw), provenance=provenance(), as_of=AT, trade_date=DAY)
    args.update(changes)
    return json.loads(api.build_eod_feature(raw, **args))


def sample(seconds=10, price=15.0):
    at = datetime.fromisoformat(AT) - timedelta(seconds=seconds)
    return dict(
        quality_state="valid_observation",
        decision_eligibility_asserted=False,
        observation=dict(
            version=api.LIVE_VERSION,
            iv30_source="india_vix",
            mode="observation",
            decision_eligibility_asserted=False,
            quote_key="NSE:INDIA VIX",
            instrument_token=123,
            raw_payload_sha256="d" * 64,
            instrument_reference_sha256="e" * 64,
            source_time=at.isoformat(),
            received_at=at.isoformat(),
            as_of=at.isoformat(),
            iv30=price / 100,
            value_percent=price,
            within_regular_time_window=True,
            session_calendar_verified=False,
            session_is_open=None,
        ),
    )


def live(samples=None, **changes):
    args = dict(provenance=provenance(), as_of=AT)
    args.update(changes)
    return json.loads(api.build_live_feature(samples or {"f" * 64: sample()}, **args))


def test_eod_percentile_rank_and_no_live_or_regime_authority():
    result = eod()
    assert result["iv_percentile"] == 100.0 and result["iv_rank"] == 100.0
    assert result["prior_observation_count"] == 120
    assert result["ivr_observation_count"] == 121
    assert result["source_time"] is None
    assert not result["session_coverage_verified"]
    assert not result["live_vrp_input_asserted"]
    assert not result["decision_eligibility_asserted"]
    assert result["regime_label"] is None


def test_eod_ivp_and_ivr_share_canonical_window_definition():
    raw = eod_history(value=10.6)
    result = json.loads(
        api.build_eod_feature(
            raw, expected_history_sha256=api.sha(raw), provenance=provenance(), as_of=AT, trade_date=DAY
        )
    )
    assert result["iv_percentile"] == pytest.approx(50.0)
    assert result["iv_rank"] == pytest.approx((10.6 - 10.01) / (11.19 - 10.01) * 100)
    assert result["ivr_observation_count"] == 121


def test_insufficient_history_returns_no_percentile_or_rank():
    result = eod(119)
    assert result["quality_state"] == "insufficient_history"
    assert result["iv_percentile"] is None and result["iv_rank"] is None


def test_ivp_uses_strict_less_on_ties():
    raw = eod_history(value=10.0)
    result = json.loads(
        api.build_eod_feature(
            raw, expected_history_sha256=api.sha(raw), provenance=provenance(), as_of=AT, trade_date=DAY
        )
    )
    assert result["iv_percentile"] == 0


def test_prior_window_bounded_to_252():
    assert eod(300)["prior_observation_count"] == 252


@pytest.mark.parametrize(
    "changes",
    [
        {"trade_date": "2026-11-25"},
        {"as_of": "2026-12-02T10:00:00+00:00"},
        {"minimum_history": 1},
        {"lookback": 119},
        {"max_age_calendar_days": 0},
        {"as_of": "2026-11-25T10:00:00"},
    ],
)
def test_eod_bad_policy_or_time_rejected(changes):
    with pytest.raises(ValueError):
        eod(**changes)


def test_materialization_must_exist_by_feature_cutoff():
    pin = provenance()
    pin["materialization_available_at"] = "2026-11-25T10:00:01+00:00"
    with pytest.raises(ValueError, match="NOT_YET_AVAILABLE"):
        eod(provenance=pin)


def test_eod_availability_is_not_inferred_from_old_trade_date():
    with pytest.raises(ValueError, match="FUTURE_HISTORY_POLICY"):
        eod(
            as_of="2026-11-25T07:00:00+00:00",
            provenance={**provenance(), "materialization_available_at": "2026-11-25T06:00:00+00:00"},
        )


def test_live_uses_actual_quote_time_not_minute_bucket():
    result = live({"a" * 64: sample(50, 14.0), "b" * 64: sample(10, 15.0)})
    assert result["iv30"] == 0.15 and result["age_seconds"] == 10
    assert result["selected_revision_id"] == "b" * 64
    assert not result["session_calendar_verified"] and not result["vrp_gate_passed"]
    assert not result["decision_eligibility_asserted"]


def test_stale_live_value_does_not_fall_back_to_eod():
    with pytest.raises(ValueError, match="STALE_LIVE"):
        live({"a" * 64: sample(301)})


@pytest.mark.parametrize(
    "field,value",
    [
        ("iv30_source", "internal_cm"),
        ("decision_eligibility_asserted", True),
        ("iv30", float("nan")),
        ("value_percent", 99.0),
        ("instrument_token", True),
        ("raw_payload_sha256", "bad"),
    ],
)
def test_live_bad_source_authority_units_and_references(field, value):
    record = sample()
    record["observation"][field] = value
    with pytest.raises(ValueError):
        live({"a" * 64: record})


def test_future_dependent_sample_cannot_be_silently_filtered():
    with pytest.raises(ValueError, match="FUTURE_OR_UNORDERED"):
        live({"a" * 64: sample(10), "b" * 64: sample(-1)})


def test_duplicate_actual_quote_time_rejected():
    with pytest.raises(ValueError, match="AMBIGUOUS"):
        live({"a" * 64: sample(), "b" * 64: sample()})


def test_rejected_native_record_not_a_live_feature():
    with pytest.raises(ValueError, match="VALID_NATIVE"):
        live({"a" * 64: dict(quality_state="rejected", decision_eligibility_asserted=False)})


def test_feature_is_deterministic():
    inputs = {"a" * 64: sample()}
    assert api.build_live_feature(inputs, provenance=provenance(), as_of=AT) == api.build_live_feature(
        deepcopy(inputs), provenance=provenance(), as_of=AT
    )
