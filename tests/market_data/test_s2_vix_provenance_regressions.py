"""Retained synthetic response checks; not Bronze publication or NSE authenticity."""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from nse_quant.market_data.india_vix_inputs import RawVixCapture, normalize_vix_capture

NOW = datetime(2026, 11, 24, 6, 0, tzinfo=UTC)


def capture():
    reference = json.dumps(
        {"exchange": "NSE", "segment": "INDICES", "tradingsymbol": "INDIA VIX", "instrument_token": 123}
    )
    payload = json.dumps({"NSE:INDIA VIX": {"instrument_token": 123, "last_price": 15.0, "timestamp": NOW.isoformat()}})
    return RawVixCapture(
        "NSE:INDIA VIX",
        123,
        hashlib.sha256(reference.encode()).hexdigest(),
        reference,
        NOW,
        NOW,
        payload,
        hashlib.sha256(payload.encode()).hexdigest(),
    )


def test_vix_units_retained_hashes_and_no_eligibility():
    raw = capture()
    value = normalize_vix_capture(raw, as_of=NOW)
    assert value.value_percent == 15.0
    assert value.iv30 == pytest.approx(0.15)
    assert value.raw_payload_sha256 == raw.payload_sha256
    assert value.instrument_reference_sha256 == raw.instrument_reference_sha256
    assert value.iv30_source == "india_vix"
    assert value.mode == "observation"
    assert value.decision_eligibility_asserted is False
    assert value.session_calendar_verified is False
    assert value.session_is_open is None


@pytest.mark.parametrize(
    "field,error",
    [
        ("payload_json", "raw_payload_hash_mismatch"),
        ("instrument_reference_json", "instrument_reference_hash_mismatch"),
    ],
)
def test_retained_bytes_tampering_rejected(field, error):
    raw = capture()
    with pytest.raises(ValueError, match=error):
        normalize_vix_capture(replace(raw, **{field: getattr(raw, field) + " "}), as_of=NOW)


def test_reference_identity_mismatch_even_with_recomputed_hash():
    raw = capture()
    reference = json.loads(raw.instrument_reference_json)
    reference["instrument_token"] = 456
    text = json.dumps(reference)
    raw = replace(
        raw, instrument_reference_json=text, instrument_reference_sha256=hashlib.sha256(text.encode()).hexdigest()
    )
    with pytest.raises(ValueError, match="vix_reference_identity_mismatch"):
        normalize_vix_capture(raw, as_of=NOW)


def test_stale_vix_not_silently_accepted():
    with pytest.raises(ValueError, match="future_or_stale_vix"):
        normalize_vix_capture(capture(), as_of=NOW + timedelta(seconds=301))
