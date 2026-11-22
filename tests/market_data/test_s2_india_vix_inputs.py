"""Critical identity/timestamp/unit cases with a mocked Kite client."""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

from nse_quant.market_data.india_vix_inputs import KiteIndiaVixProvider, normalize_vix_capture

NOW = datetime(2026, 1, 2, 6, tzinfo=UTC)


def captured(**changes):
    kite = Mock()
    kite.instruments.return_value = [
        dict(exchange="NSE", segment="INDICES", tradingsymbol="INDIA VIX", instrument_token=999)
    ]
    quote = dict(instrument_token=999, last_price=18.0, timestamp="2026-01-02T11:29:59")
    quote.update(changes)
    kite.quote.return_value = {"NSE:INDIA VIX": quote}
    provider = KiteIndiaVixProvider(kite, quote_key="NSE:INDIA VIX", tradingsymbol="INDIA VIX", clock=lambda: NOW)
    return provider.capture(), kite


def test_vix_normalization_keeps_source_and_receive_time_and_decimal_units():
    raw, kite = captured()
    value = normalize_vix_capture(raw, as_of=NOW)
    assert value.iv30 == 0.18 and value.value_percent == 18
    assert value.source_time == NOW - timedelta(seconds=1)
    assert value.received_at == NOW and value.iv30_source == "india_vix"
    assert value.within_regular_time_window and not value.session_calendar_verified
    assert value.session_is_open is None and value.decision_eligibility_asserted is False
    assert raw.payload_json and raw.instrument_reference_json
    kite.instruments.assert_called_once_with("NSE")
    kite.quote.assert_called_once_with(["NSE:INDIA VIX"])


@pytest.mark.parametrize(
    "changes",
    [
        {"last_price": 0},
        {"last_price": True},
        {"instrument_token": 123},
        {"timestamp": None},
        {"timestamp": "2026-01-02T11:30:01"},
        {"timestamp": "2026-01-02T11:20:00"},
    ],
)
def test_missing_invalid_stale_or_future_vix_never_normalizes(changes):
    raw, _ = captured(**changes)
    with pytest.raises(ValueError):
        normalize_vix_capture(raw, as_of=NOW)


def test_raw_capture_remains_available_when_normalization_fails():
    raw, _ = captured(timestamp=None)
    assert json.loads(raw.payload_json)[raw.quote_key]["timestamp"] is None
    with pytest.raises(ValueError, match="timestamp_missing"):
        normalize_vix_capture(raw, as_of=NOW)
    assert raw.payload_sha256 == hashlib.sha256(raw.payload_json.encode()).hexdigest()


def test_payload_and_instrument_reference_tampering_are_rejected():
    raw, _ = captured()
    with pytest.raises(ValueError, match="payload_hash"):
        normalize_vix_capture(replace(raw, payload_json="{}"), as_of=NOW)
    with pytest.raises(ValueError, match="reference_hash"):
        normalize_vix_capture(replace(raw, instrument_reference_json="{}"), as_of=NOW)


def test_ambiguous_index_identity_is_rejected_before_quote_request():
    raw, kite = captured()
    kite.reset_mock()
    row = json.loads(raw.instrument_reference_json)
    kite.instruments.return_value = [row, row]
    with pytest.raises(ValueError, match="unique_india_vix"):
        KiteIndiaVixProvider(kite, quote_key=raw.quote_key, tradingsymbol="INDIA VIX").capture()
    kite.quote.assert_not_called()
