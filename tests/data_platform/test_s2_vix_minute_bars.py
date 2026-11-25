"""Minute aggregation boundary tests; native VIX replay is substituted here."""

from datetime import UTC, datetime, timedelta

import pytest

from nse_quant.data_platform import s2_vix_minute_bars as api


def test_source_time_sort_and_no_gap_fill(monkeypatch):
    at = datetime(2026, 11, 24, 10, tzinfo=UTC)
    revisions = ["a" * 64, "b" * 64, "c" * 64]
    records = dict(
        zip(
            revisions,
            [(at + timedelta(seconds=20), 0.16), (at + timedelta(seconds=10), 0.15), (at + timedelta(minutes=2), 0.17)],
            strict=True,
        )
    )

    def replay(*args, revision_id):
        stamp, value = records[revision_id]
        return dict(
            quality_state="valid_observation",
            observation=dict(
                source_time=stamp.isoformat(),
                iv30=value,
                iv30_source="india_vix",
                instrument_token=123,
                decision_eligibility_asserted=False,
            ),
        )

    monkeypatch.setattr(api.vix, "replay_vix_silver", replay)
    raw = api.build_minute_bars(None, None, revision_ids=revisions)
    value = api.replay_minute_bars(None, None, raw, expected_sha256=api.base.sha(raw))
    assert len(value["bars"]) == 2
    assert value["bars"][0]["open"] == 0.15
    assert value["bars"][0]["close"] == 0.16
    assert not value["daily_close_asserted"]
    records[revisions[0]] = records[revisions[1]]
    with pytest.raises(ValueError, match="AMBIGUOUS"):
        api.build_minute_bars(None, None, revision_ids=revisions)


def test_rejected_observation_not_a_bar_input(monkeypatch):
    monkeypatch.setattr(api.vix, "replay_vix_silver", lambda *args, **kwargs: dict(quality_state="rejected"))
    with pytest.raises(ValueError, match="REJECTED"):
        api.build_minute_bars(None, None, revision_ids=["a" * 64])
