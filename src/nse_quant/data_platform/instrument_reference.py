"""Pure bounded offline Kite CSV reference normalization, original FS2b1 policy."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import asdict, dataclass
from datetime import date

PARSER_VERSION = "kite-instruments-csv@1"
RESOLVER_VERSION = "pinned-token-reference@1"
MAX_ARTIFACT_BYTES = 16_777_216
MAX_ROWS = 200_000
COLUMNS = (
    "instrument_token",
    "exchange_token",
    "tradingsymbol",
    "name",
    "last_price",
    "expiry",
    "strike",
    "tick_size",
    "lot_size",
    "instrument_type",
    "segment",
    "exchange",
)


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class InstrumentReference:
    row_ordinal: int
    instrument_token: int
    exchange_token: str
    tradingsymbol: str
    provider_name: str
    last_price_decimal: str
    expiry: str | None
    strike_decimal: str
    tick_size_decimal: str
    lot_size: int
    instrument_type: str
    segment: str
    exchange: str
    source_row_hash: str


@dataclass(frozen=True)
class ReferenceSnapshot:
    classification: str
    reason_code: str
    records: tuple[InstrumentReference, ...] = ()
    failure_row_ordinal: int | None = None


@dataclass(frozen=True)
class TokenResolution:
    resolver_version: str
    reference_revision_id: str
    instrument_token: int
    status: str
    reason_code: str
    candidate_row_ordinals: tuple[int, ...]
    evidence_mode: str = "PINNED_SNAPSHOT_ONLY"


def _integer(raw: str, maximum: int, *, positive: bool = False) -> int:
    if not re.fullmatch(r"[0-9]{1,20}", raw):
        raise ValueError("INVALID_INTEGER")
    value = int(raw)
    if value > maximum or (positive and value == 0):
        raise ValueError("INTEGER_RANGE")
    return value


def _decimal(raw: str) -> str:
    if len(raw) > 64 or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", raw):
        raise ValueError("INVALID_DECIMAL")
    return raw


def parse_instruments(raw: bytes) -> ReferenceSnapshot:
    """Original offline v1 requires nonempty decimals, including strike.

    Blank strike quarantines: do not silently replace it with zero or change v1
    semantics. Native FS2b3 has a different explicitly nullable CSV contract.
    """
    if not isinstance(raw, bytes):
        raise TypeError("Exact bytes required")
    if len(raw) > MAX_ARTIFACT_BYTES:
        return ReferenceSnapshot("quarantine", "ARTIFACT_BYTE_LIMIT")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError:
        return ReferenceSnapshot("quarantine", "INVALID_UTF8")
    if "\x00" in text:
        return ReferenceSnapshot("quarantine", "NUL_BYTE")
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    records: list[InstrumentReference] = []
    ordinal: int | None = None
    try:
        header = next(reader, None)
        if header is None:
            return ReferenceSnapshot("quarantine", "EMPTY_ARTIFACT")
        if tuple(v.strip() for v in header) != COLUMNS:
            return ReferenceSnapshot("quarantine", "UNSUPPORTED_HEADER")
        for ordinal, row in enumerate(reader):
            if ordinal >= MAX_ROWS:
                return ReferenceSnapshot("quarantine", "ROW_COUNT_LIMIT", (), ordinal)
            if len(row) != len(COLUMNS):
                return ReferenceSnapshot("quarantine", "COLUMN_COUNT", (), ordinal)
            if any(len(value) > 4096 for value in row):
                return ReferenceSnapshot("quarantine", "FIELD_SIZE_LIMIT", (), ordinal)
            values = dict(zip(COLUMNS, row, strict=True))
            for key in ("tradingsymbol", "instrument_type", "segment", "exchange"):
                value = values[key]
                if not value or value != value.strip() or any(ord(c) < 32 for c in value):
                    return ReferenceSnapshot("quarantine", "INVALID_IDENTIFIER", (), ordinal)
            token = _integer(values["instrument_token"], 2**32 - 1, positive=True)
            _integer(values["exchange_token"], 2**32 - 1)
            lot = _integer(values["lot_size"], 2**63 - 1, positive=True)
            expiry = values["expiry"] or None
            if expiry is not None:
                if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", expiry):
                    raise ValueError("INVALID_EXPIRY")
                try:
                    date.fromisoformat(expiry)
                except ValueError:
                    raise ValueError("INVALID_EXPIRY") from None
            elif values["instrument_type"] in {"CE", "PE", "FUT"}:
                raise ValueError("MISSING_DERIVATIVE_EXPIRY")
            records.append(
                InstrumentReference(
                    ordinal,
                    token,
                    values["exchange_token"],
                    values["tradingsymbol"],
                    values["name"],
                    _decimal(values["last_price"]),
                    expiry,
                    _decimal(values["strike"]),
                    _decimal(values["tick_size"]),
                    lot,
                    values["instrument_type"],
                    values["segment"],
                    values["exchange"],
                    fingerprint(row),
                )
            )
    except csv.Error:
        return ReferenceSnapshot("quarantine", "INVALID_CSV", (), ordinal)
    except ValueError as error:
        return ReferenceSnapshot("quarantine", str(error), (), ordinal)
    if not records:
        return ReferenceSnapshot("quarantine", "EMPTY_SNAPSHOT")
    return ReferenceSnapshot("normalized", "PARSED", tuple(records))


def resolve_token(
    snapshot: ReferenceSnapshot,
    *,
    reference_revision_id: str,
    instrument_token: int,
) -> TokenResolution:
    if not re.fullmatch(r"[0-9a-f]{64}", reference_revision_id):
        raise ValueError("PINNED_REFERENCE_REVISION_REQUIRED")
    if type(instrument_token) is not int or not 0 < instrument_token < 2**32:
        raise ValueError("INVALID_PROVIDER_TOKEN")
    candidates = tuple(
        r.row_ordinal for r in snapshot.records if r.instrument_token == instrument_token
    )
    if snapshot.classification != "normalized":
        status, reason, candidates = "unresolved", "REFERENCE_QUARANTINED", ()
    elif not candidates:
        status, reason = "unresolved", "TOKEN_NOT_IN_PINNED_SNAPSHOT"
    elif len(candidates) > 1:
        status, reason = "ambiguous", "MULTIPLE_TOKEN_ROWS"
    else:
        status, reason = "matched", "UNIQUE_TOKEN_ROW"
    return TokenResolution(
        RESOLVER_VERSION, reference_revision_id, instrument_token, status, reason, candidates
    )


def snapshot_json(snapshot: ReferenceSnapshot) -> str:
    return canonical(asdict(snapshot))
