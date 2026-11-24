import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from nse_quant.analytics import constant_maturity_inputs as cm
from nse_quant.data_platform import surface_evidence_bundle as bundle


def evidence():
    at = datetime(2026, 11, 24, tzinfo=UTC)
    doc: dict[str, Any] = dict(
        policy=dict(
            as_of=at, max_age_seconds=300, max_source_gap_seconds=30, kernel=cm.VERSION, delta=cm.DELTA_CONVENTION
        ),
        premiums=[],
        forwards=[],
        calendar=dict(source="fixture-calendar", available_at=at, closes=[]),
    )
    for days in (25, 40, 80, 100):
        close = at + timedelta(days=days)
        doc["calendar"]["closes"].append(close)
        doc["forwards"].append(
            dict(
                expiry_close=close,
                kind="matched_forward_observation",
                rate=dict(
                    annual_rate=0.05,
                    convention="annual_continuously_compounded",
                    source="fixture-rate",
                    available_at=at,
                ),
                evidence=dict(
                    underlying="NIFTY", forward=100, source="fixture-forward", source_time=at, received_at=at
                ),
            )
        )
        for kind in ("CE", "PE"):
            for strike in (90, 95, 100, 105, 110):
                price = cm.black76_price(100, strike, days / 365, 0.05, 0.25, kind)
                doc["premiums"].append(
                    dict(
                        token=len(doc["premiums"]) + 1,
                        underlying="NIFTY",
                        batch_id="test",
                        expiry_close=close,
                        strike=strike,
                        option_type=kind,
                        bid=price,
                        ask=price,
                        source_time=at,
                        received_at=at,
                    )
                )
    return doc


def test_surface_roundtrip():
    doc = evidence()
    raw = bundle.build_bundle(doc)
    assert bundle.build_bundle(doc) == raw
    result = bundle.replay_bundle(raw, expected_sha256=bundle.sha256(raw))
    assert result["iv30"]["iv"] == pytest.approx(0.25)
    assert result["iv90"]["iv"] == pytest.approx(0.25)
    assert result["rr25"] == pytest.approx(0)
    assert result["decision_eligibility_asserted"] is False


def test_rehashed_output_still_must_recompute():
    raw = bundle.build_bundle(evidence())
    doc = json.loads(raw)
    doc["result"]["rr25"] = 42
    changed = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(ValueError, match="REPLAY_MISMATCH"):
        bundle.replay_bundle(changed, expected_sha256=bundle.sha256(changed))
    with pytest.raises(ValueError, match="PIN"):
        bundle.replay_bundle(changed, expected_sha256=bundle.sha256(raw))


@pytest.mark.parametrize("gap", ["forward", "calendar", "rate", "stale", "maturity", "wing"])
def test_missing_or_invalid_evidence(gap):
    doc = evidence()
    if gap == "forward":
        doc["forwards"].pop()
    elif gap == "calendar":
        doc["calendar"]["closes"].pop()
    elif gap == "rate":
        doc["forwards"][0]["rate"]["available_at"] += timedelta(seconds=1)
    elif gap == "stale":
        doc["premiums"][0]["source_time"] -= timedelta(seconds=301)
    elif gap == "maturity":
        close = doc["calendar"]["closes"][-1]
        doc["premiums"] = [q for q in doc["premiums"] if q["expiry_close"] != close]
    else:
        doc["premiums"] = [q for q in doc["premiums"] if q["strike"] == 100]
    with pytest.raises(ValueError):
        bundle.build_bundle(doc)


def test_synthetic_forward_uses_retained_pair():
    doc = evidence()
    first = doc["forwards"][0]
    first["kind"] = "synthetic_parity"
    first["evidence"] = dict(call_token=3, put_token=8)
    raw = bundle.build_bundle(doc)
    assert bundle.replay_bundle(raw, expected_sha256=bundle.sha256(raw))["iv30"]["iv"] == pytest.approx(0.25)
    first["evidence"]["put_token"] = 18
    with pytest.raises(ValueError, match="PAIR_NOT_LINKED"):
        bundle.build_bundle(doc)
