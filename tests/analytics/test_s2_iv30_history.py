import json
from datetime import date, timedelta

import pytest

from nse_quant.analytics import s2_iv30_history as api


def build(raw=None, **changes):
    if raw is None:
        raw = b"day,close\n2026-11-20,15\n2026-11-23,16\n"
    args = dict(
        raw_csv=raw,
        expected_raw_sha256=api.sha(raw),
        source_reference="synthetic-eod-file",
        received_at="2026-11-24T00:00:00+00:00",
        as_of="2026-11-25T00:00:00+00:00",
        date_column="day",
        close_column="close",
    )
    args.update(changes)
    return api.build_history(**args)


def test_retained_bytes_source_units_and_replay():
    raw = build()
    value = api.replay_history(raw, expected_sha256=api.sha(raw))
    assert value["rows"][0]["iv30"] == 0.15
    assert value["iv30_source"] == "india_vix"
    assert not value["decision_eligibility_asserted"]
    assert not value["historical_availability_asserted"]


def test_rehashed_modified_output_must_recompute():
    doc = json.loads(build())
    doc["rows"][0]["iv30"] = 9
    raw = api.canonical(doc)
    with pytest.raises(ValueError, match="REPLAY"):
        api.replay_history(raw, expected_sha256=api.sha(raw))


@pytest.mark.parametrize(
    "text",
    [
        "day,close\n2026-11-20,nan\n",
        "day,close\n2026-11-20,-1\n",
        "day,close\n2026-11-20,15\n2026-11-20,16\n",
        "day,close\n2026-11-25,15\n",
    ],
)
def test_bad_or_not_completed_rows_rejected(text):
    with pytest.raises(ValueError):
        build(text.encode())


def test_availability_never_inferred_from_trade_date():
    with pytest.raises(ValueError, match="AVAILABLE"):
        build(received_at="2026-11-26T00:00:00+00:00")


def test_ivp_minimum_history_and_no_future_rows():
    start = date(2025, 1, 1)
    lines = ["day,close"] + [f"{start + timedelta(days=i)},{10 + i}" for i in range(122)]
    raw = build(("\n".join(lines) + "\n").encode())
    assert (
        api.iv_percentile(raw, expected_sha256=api.sha(raw), trade_date=(start + timedelta(days=120)).isoformat())
        == 100
    )
    with pytest.raises(ValueError, match="INSUFFICIENT"):
        api.iv_percentile(raw, expected_sha256=api.sha(raw), trade_date=(start + timedelta(days=119)).isoformat())
