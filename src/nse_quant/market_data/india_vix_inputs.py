"""Explicit, read-only Kite India VIX acquisition and pure normalization.

Raw response retention is separate from normalization. These values are not
Bronze/Silver/Gold publications and do not authorize entries or IV-series mixing.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Any, Literal

from nse_quant.core.constants import IST
from nse_quant.market_data.kite_timestamps import normalize_kite_rest_timestamp

VERSION = "kite_india_vix_observation_v1"


@dataclass(frozen=True)
class RawVixCapture:
    quote_key: str
    instrument_token: int
    instrument_reference_sha256: str
    instrument_reference_json: str
    requested_at: datetime
    received_at: datetime
    payload_json: str
    payload_sha256: str


@dataclass(frozen=True)
class IndiaVixObservation:
    as_of: datetime
    source_time: datetime
    received_at: datetime
    value_percent: float
    iv30: float
    raw_payload_sha256: str
    instrument_reference_sha256: str
    instrument_token: int
    quote_key: str
    within_regular_time_window: bool
    session_calendar_verified: bool
    session_is_open: bool | None
    version: str = VERSION
    iv30_source: str = "india_vix"
    mode: str = "observation"
    decision_eligibility_asserted: Literal[False] = False


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("aware_datetime_required")
    return value.astimezone(UTC)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError("unsupported_raw_payload_value")


class KiteIndiaVixProvider:
    """Resolve one NSE index by supplied configuration; never hard-code a token."""

    def __init__(
        self, kite: Any, *, quote_key: str, tradingsymbol: str, clock: Callable[[], datetime] | None = None
    ) -> None:
        if quote_key != "NSE:INDIA VIX" or tradingsymbol != "INDIA VIX":
            raise ValueError("consistent_nse_index_configuration_required")
        self.kite = kite
        self.quote_key = quote_key
        self.tradingsymbol = tradingsymbol
        self.clock = clock or (lambda: datetime.now(UTC))

    def capture(self) -> RawVixCapture:
        instruments = self.kite.instruments("NSE")
        matches = [
            row
            for row in instruments
            if row.get("exchange") == "NSE"
            and row.get("segment") == "INDICES"
            and row.get("tradingsymbol") == self.tradingsymbol
        ]
        if len(matches) != 1 or type(matches[0].get("instrument_token")) is not int:
            raise ValueError("unique_india_vix_index_identity_required")
        token = matches[0]["instrument_token"]
        if token <= 0:
            raise ValueError("positive_index_token_required")
        reference = json.dumps(
            matches[0], sort_keys=True, separators=(",", ":"), default=_json_default, allow_nan=False
        )
        requested = _aware(self.clock())
        response = self.kite.quote([self.quote_key])
        received = _aware(self.clock())
        if received < requested:
            raise ValueError("capture_clock_moved_backwards")
        payload = json.dumps(response, sort_keys=True, separators=(",", ":"), default=_json_default, allow_nan=False)
        return RawVixCapture(
            self.quote_key,
            token,
            hashlib.sha256(reference.encode()).hexdigest(),
            reference,
            requested,
            received,
            payload,
            hashlib.sha256(payload.encode()).hexdigest(),
        )


def normalize_vix_capture(
    capture: RawVixCapture, *, as_of: datetime, max_age_seconds: float = 300, session_is_open: bool | None = None
) -> IndiaVixObservation:
    as_of = _aware(as_of)
    requested, received = _aware(capture.requested_at), _aware(capture.received_at)
    if (
        isinstance(max_age_seconds, bool)
        or not isinstance(max_age_seconds, (float, int))
        or not math.isfinite(max_age_seconds)
        or max_age_seconds <= 0
    ):
        raise ValueError("invalid_freshness_limit")
    if session_is_open is not None and type(session_is_open) is not bool:
        raise ValueError("explicit_session_flag_required")
    if not requested <= received <= as_of:
        raise ValueError("future_or_unordered_capture")
    if hashlib.sha256(capture.payload_json.encode()).hexdigest() != capture.payload_sha256:
        raise ValueError("raw_payload_hash_mismatch")
    if hashlib.sha256(capture.instrument_reference_json.encode()).hexdigest() != capture.instrument_reference_sha256:
        raise ValueError("instrument_reference_hash_mismatch")
    reference = json.loads(capture.instrument_reference_json)
    if (
        not isinstance(reference, dict)
        or reference.get("exchange") != "NSE"
        or reference.get("segment") != "INDICES"
        or reference.get("tradingsymbol") != "INDIA VIX"
        or type(reference.get("instrument_token")) is not int
        or reference["instrument_token"] != capture.instrument_token
        or type(capture.instrument_token) is not int
        or capture.instrument_token <= 0
        or capture.quote_key != "NSE:INDIA VIX"
    ):
        raise ValueError("vix_reference_identity_mismatch")
    response = json.loads(capture.payload_json)
    quote = response.get(capture.quote_key) if isinstance(response, dict) else None
    if (
        not isinstance(quote, dict)
        or type(quote.get("instrument_token")) is not int
        or quote.get("instrument_token") != capture.instrument_token
    ):
        raise ValueError("vix_quote_identity_mismatch")
    value = quote.get("last_price")
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
        raise ValueError("invalid_vix_value")
    source = normalize_kite_rest_timestamp(quote.get("timestamp"), field="india_vix.timestamp")
    if source is None:
        raise ValueError("vix_source_timestamp_missing")
    if source > received or (as_of - source).total_seconds() > max_age_seconds:
        raise ValueError("future_or_stale_vix")
    wall = source.astimezone(IST).time().replace(tzinfo=None)
    within = time(9, 15) <= wall <= time(15, 30)
    return IndiaVixObservation(
        as_of,
        source,
        received,
        float(value),
        float(value) / 100,
        capture.payload_sha256,
        capture.instrument_reference_sha256,
        capture.instrument_token,
        capture.quote_key,
        within,
        session_is_open is not None,
        session_is_open,
    )
