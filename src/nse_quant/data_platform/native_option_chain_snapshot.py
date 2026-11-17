"""Native option-chain snapshot artifact codec; retained evidence, not market truth."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

VERSION = "native-option-chain-snapshot@1"
MAX_QUOTES = 1000
MAX_BYTES = 1_048_576
MAX_LABEL = 128
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class Rejected(ValueError):
    """Explicit rejection; never a silent acceptance."""


def pin(value: object) -> bool:
    return isinstance(value, str) and bool(_HEX64.fullmatch(value))


def json_safe(value: Any) -> Any:
    """Return a deterministic JSON-serializable representation of value."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return str(value)


def canonical(value: Any) -> bytes:
    return json.dumps(
        json_safe(value),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _aware(value: object) -> datetime:
    if not isinstance(value, str):
        raise Rejected("AWARE_INSTANT_REQUIRED")
    try:
        instant = datetime.fromisoformat(value)
    except ValueError as exc:
        raise Rejected("AWARE_INSTANT_REQUIRED") from exc
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise Rejected("AWARE_INSTANT_REQUIRED")
    return instant


def _finite(value: object) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise Rejected("FINITE_FLOAT_REQUIRED")
    return value


def _date(value: object) -> date:
    if not isinstance(value, str):
        raise Rejected("CALENDAR_DATE_REQUIRED")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise Rejected("CALENDAR_DATE_REQUIRED") from exc


def _validate_quote(quote: object) -> None:
    if not isinstance(quote, dict):
        raise Rejected("OPTION_QUOTE_OBJECT_REQUIRED")
    instrument = quote.get("instrument")
    if not isinstance(instrument, dict):
        raise Rejected("INSTRUMENT_OBJECT_REQUIRED")
    if set(instrument) != {
        "tradingsymbol",
        "instrument_token",
        "underlying",
        "expiry",
        "strike",
        "option_type",
        "lot_size",
    }:
        raise Rejected("INSTRUMENT_FIELDS_REQUIRED")
    if (
        type(instrument["tradingsymbol"]) is not str
        or not 0 < len(instrument["tradingsymbol"].encode()) <= MAX_LABEL
        or type(instrument["instrument_token"]) is not int
        or isinstance(instrument["instrument_token"], bool)
        or type(instrument["underlying"]) is not str
        or not 0 < len(instrument["underlying"].encode()) <= MAX_LABEL
    ):
        raise Rejected("INSTRUMENT_IDENTITY_REQUIRED")
    _date(instrument["expiry"])
    strike = _finite(instrument["strike"])
    if strike < 0:
        raise Rejected("NON_NEGATIVE_STRIKE_REQUIRED")
    if instrument["option_type"] not in ("CE", "PE"):
        raise Rejected("OPTION_TYPE_REQUIRED")
    lot = instrument["lot_size"]
    if type(lot) is not int or isinstance(lot, bool) or lot <= 0:
        raise Rejected("POSITIVE_LOT_SIZE_REQUIRED")
    for field in ("ltp", "bid", "ask"):
        value = quote.get(field)
        if value is not None:
            price = _finite(value)
            if price < 0:
                raise Rejected("NON_NEGATIVE_PRICE_REQUIRED")
    for field in ("volume", "oi"):
        value = quote.get(field)
        if value is not None and (type(value) is not int or isinstance(value, bool) or value < 0):
            raise Rejected("NON_NEGATIVE_INTEGER_REQUIRED")
    for field in ("exchange_ts", "trade_ts"):
        value = quote.get(field)
        if value is not None:
            _aware(value)
    _aware(quote.get("received_at"))
    if set(quote) != {
        "instrument",
        "ltp",
        "bid",
        "ask",
        "volume",
        "oi",
        "exchange_ts",
        "trade_ts",
        "received_at",
    }:
        raise Rejected("QUOTE_FIELDS_REQUIRED")


def validate_document(document: object) -> None:
    if not isinstance(document, dict):
        raise Rejected("SNAPSHOT_OBJECT_REQUIRED")
    if set(document) != {"ts", "underlying", "spot", "expiry", "is_market_open", "quotes"}:
        raise Rejected("SNAPSHOT_FIELDS_REQUIRED")
    _aware(document["ts"])
    if type(document["underlying"]) is not str or not 0 < len(document["underlying"].encode()) <= MAX_LABEL:
        raise Rejected("UNDERLYING_REQUIRED")
    spot = _finite(document["spot"])
    if spot <= 0:
        raise Rejected("POSITIVE_SPOT_REQUIRED")
    _date(document["expiry"])
    if type(document["is_market_open"]) is not bool:
        raise Rejected("MARKET_SESSION_FLAG_REQUIRED")
    quotes = document["quotes"]
    if not isinstance(quotes, list) or not 1 <= len(quotes) <= MAX_QUOTES:
        raise Rejected("OPTION_QUOTE_BOUND")
    for quote in quotes:
        _validate_quote(quote)


def make_snapshot(source_label: str, document: object) -> bytes:
    if type(source_label) is not str or not 0 < len(source_label.encode()) <= MAX_LABEL:
        raise Rejected("EXPLICIT_SOURCE_LABEL_REQUIRED")
    validate_document(document)
    payload = canonical({"source_label": source_label, "snapshot": document})
    if len(payload) > MAX_BYTES:
        raise Rejected("SNAPSHOT_BYTE_BOUND")
    return payload


def snapshot_id(payload: bytes) -> str:
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_BYTES:
        raise Rejected("SNAPSHOT_BYTE_BOUND")
    return sha(payload)


def replay_snapshot(raw: bytes, *, expected_snapshot_id: str) -> dict[str, Any]:
    if not pin(expected_snapshot_id) or sha(raw) != expected_snapshot_id:
        raise Rejected("SNAPSHOT_HASH_MISMATCH")
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Rejected("MALFORMED_SNAPSHOT") from exc
    validate_document(document.get("snapshot") if isinstance(document, dict) else None)
    if (
        not isinstance(document, dict)
        or set(document) != {"source_label", "snapshot"}
        or type(document["source_label"]) is not str
    ):
        raise Rejected("SNAPSHOT_ENVELOPE_REQUIRED")
    return document


def derive_records(
    raw: bytes,
    *,
    snapshot_id: str,
    capture_event_id: str,
    envelope_hash: str,
) -> tuple[bytes, ...]:
    document = replay_snapshot(raw, expected_snapshot_id=snapshot_id)
    snapshot = document["snapshot"]
    records = []
    for ordinal, quote in enumerate(snapshot["quotes"]):
        records.append(
            canonical(
                {
                    "snapshot_id": snapshot_id,
                    "capture_event_id": capture_event_id,
                    "envelope_hash": envelope_hash,
                    "source_ordinal": ordinal,
                    "stored_fields": {
                        "ts": snapshot["ts"],
                        "underlying": snapshot["underlying"],
                        "spot": snapshot["spot"],
                        "expiry": snapshot["expiry"],
                        "is_market_open": snapshot["is_market_open"],
                        "quote": quote,
                    },
                }
            )
        )
    return tuple(records)
