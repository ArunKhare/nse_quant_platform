"""Pure exact legacy Silver record projection; no market-data eligibility claims."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from typing import Any

VERSION = "legacy-market-silver@1"
SOURCE_VERSION = "legacy-market-snapshot@1"
MAX_ROWS = 1000
MAX_ROW_BYTES = 524288
MAX_INPUT_BYTES = 4194304
MAX_SET_BYTES = 8388608
OPTION_NAMES = (
    "run_id",
    "ts",
    "underlying",
    "expiry",
    "strike",
    "option_type",
    "tradingsymbol",
    "instrument_token",
    "lot_size",
    "spot",
    "ltp",
    "bid",
    "ask",
    "volume",
    "oi",
    "iv",
    "delta",
    "gamma",
    "vega",
    "theta",
    "quote_status",
    "payload_json",
)
CANDLE_NAMES = (
    "instrument_token",
    "symbol",
    "interval",
    "ts",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "oi",
)
DERIVED = frozenset(("iv", "delta", "gamma", "vega", "theta"))
FLOATS = DERIVED | {"strike", "spot", "ltp", "bid", "ask", "open", "high", "low", "close"}
INTEGERS = frozenset(("instrument_token", "lot_size", "volume", "oi"))
SOURCE_FIELDS = frozenset(
    (
        "snapshot_id",
        "ordinal",
        "table",
        "stored_fields",
        "legacy_derived_fields",
        "source_time_semantics",
        "original_provider_bytes_retained",
        "identity_verified",
        "availability_evidence_verified",
        "decision_eligibility_asserted",
    )
)
DEFINITION = (
    VERSION,
    SOURCE_VERSION,
    "complete legacy stored-record projection with exact source ordinals",
    "legacy floats retain binary64 hex; analytics remain legacy-derived",
    "stored ts is not availability; flags never grant identity/publication/decision admission",
    OPTION_NAMES,
    CANDLE_NAMES,
)


class SilverRejected(ValueError):
    """Fixed diagnostic codes only; execution failures propagate."""


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pin(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _clock(value: Any) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise SilverRejected("AWARE_CLOCK_REQUIRED")
    return value.astimezone(UTC).isoformat()


@dataclass(frozen=True)
class LegacyBronzePins:
    capture_event_id: str
    envelope_hash: str
    snapshot_id: str

    def __post_init__(self) -> None:
        if not all(pin(x) for x in asdict(self).values()):
            raise SilverRejected("EXACT_LEGACY_BRONZE_PINS_REQUIRED")

    @property
    def scope_id(self) -> str:
        return sha(canonical([VERSION, asdict(self)]))


def definition_sha256() -> str:
    return sha(canonical(DEFINITION))


def _validate_cells(fields: dict[str, Any]) -> None:
    for name, value in fields.items():
        if value is None:
            continue
        if type(value) is not str or len(value.encode()) > 65536:
            raise SilverRejected("STORED_CELL_CONTRACT")
        if name in FLOATS:
            number = float.fromhex(value)
            if not math.isfinite(number) or number.hex() != value:
                raise SilverRejected("EXACT_FINITE_BINARY64_HEX_REQUIRED")
        elif name in INTEGERS:
            number_int = int(value)
            bound = 2**31 if name == "lot_size" else 2**63
            if str(number_int) != value or not -bound <= number_int < bound:
                raise SilverRejected("EXACT_STORED_INTEGER_REQUIRED")
        elif name == "ts":
            if _clock(datetime.fromisoformat(value)) != value:
                raise SilverRejected("EXACT_STORED_UTC_INSTANT_REQUIRED")
        elif name == "expiry" and date.fromisoformat(value).isoformat() != value:
            raise SilverRejected("EXACT_STORED_DATE_REQUIRED")


def derive_records(
    observations: tuple[dict[str, Any], ...],
    *,
    pins: LegacyBronzePins,
) -> tuple[bytes, ...]:
    """Pure untrusted-input projection, not a substitute for native source verification."""
    if type(pins) is not LegacyBronzePins:
        raise SilverRejected("TYPED_SOURCE_PINS_REQUIRED")
    pins = LegacyBronzePins(**asdict(pins))
    if type(observations) is not tuple or not 1 <= len(observations) <= MAX_ROWS:
        raise SilverRejected("BOUNDED_COMPLETE_OBSERVATIONS_REQUIRED")
    if len(canonical(observations)) > MAX_INPUT_BYTES:
        raise SilverRejected("SOURCE_OBSERVATION_BYTE_BOUND")
    output: list[bytes] = []
    seen: set[bytes] = set()
    table: str | None = None
    try:
        for ordinal, item in enumerate(observations):
            if type(item) is not dict or set(item) != SOURCE_FIELDS:
                raise SilverRejected("SOURCE_OBSERVATION_SCHEMA")
            names = OPTION_NAMES if item["table"] == "option_stream" else CANDLE_NAMES
            if (
                item["table"] not in ("option_stream", "spot_candles")
                or (table is not None and table != item["table"])
                or type(item["ordinal"]) is not int
                or item["ordinal"] != ordinal
                or item["snapshot_id"] != pins.snapshot_id
                or item["source_time_semantics"] != "LEGACY_STORED_TS_NOT_INDEPENDENT_AVAILABILITY"
                or any(
                    item[k] is not False
                    for k in (
                        "original_provider_bytes_retained",
                        "identity_verified",
                        "availability_evidence_verified",
                        "decision_eligibility_asserted",
                    )
                )
            ):
                raise SilverRejected("SOURCE_OBSERVATION_CONTRACT")
            fields = item["stored_fields"]
            if type(fields) is not dict or set(fields) != set(names):
                raise SilverRejected("EXACT_STORED_FIELD_MEMBERSHIP_REQUIRED")
            _validate_cells(fields)
            if item["legacy_derived_fields"] != {k: v for k, v in fields.items() if k in DERIVED}:
                raise SilverRejected("LEGACY_ANALYTICS_PROJECTION_MISMATCH")
            key_names = (
                ("run_id", "ts", "instrument_token")
                if names == OPTION_NAMES
                else ("instrument_token", "interval", "ts")
            )
            key = [fields[k] for k in key_names]
            if any(x is None for x in key) or canonical(key) in seen:
                raise SilverRejected("DUPLICATE_OR_UNKNOWN_STORED_KEY")
            seen.add(canonical(key))
            table = item["table"]
            body = dict(
                version=VERSION,
                source_pins=asdict(pins),
                source_ordinal=ordinal,
                source_table=table,
                stored_key=key,
                stored_fields=fields,
                legacy_derived_fields=item["legacy_derived_fields"],
                classification="RETAINED_LEGACY_OBSERVATION_NOT_MARKET_VALIDATED",
                canonical_contract_id=None,
                availability_evidence_verified=False,
                economic_validity_verified=False,
                publication_asserted=False,
                decision_eligibility_asserted=False,
            )
            raw = canonical(body)
            if len(raw) > MAX_ROW_BYTES:
                raise SilverRejected("SILVER_ROW_BYTE_BOUND")
            output.append(raw)
        if sum(map(len, output)) > MAX_SET_BYTES:
            raise SilverRejected("SILVER_SET_BYTE_BOUND")
        return tuple(output)
    except SilverRejected:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise SilverRejected("MALFORMED_SOURCE_OBSERVATIONS") from None


def record_values(raw: bytes) -> tuple[object, ...]:
    """Materialized SQL indices are derived, never allowed to diverge from full bytes."""
    body = json.loads(raw)
    fields = body["stored_fields"]
    return (
        sha(raw),
        body["source_ordinal"],
        body["source_table"],
        int(fields["instrument_token"]),
        datetime.fromisoformat(fields["ts"]),
        None if fields["volume"] is None else int(fields["volume"]),
        None if fields["oi"] is None else int(fields["oi"]),
        raw,
    )
