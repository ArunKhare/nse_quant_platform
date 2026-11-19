"""Pure native HTTP content decoding and typed CSV observations, no identity guessing."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zlib
from dataclasses import dataclass
from datetime import date

DECODER_VERSION = "kite-reference-content@1"
CSV_VERSION = "kite-native-reference-csv@1"
MAX_ENCODED_BYTES = 8_388_608
MAX_DECODED_BYTES = 16_777_216
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


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class ReferenceRow:
    row_ordinal: int
    instrument_token: int
    exchange_token: str
    tradingsymbol: str
    provider_name: str
    last_price_decimal: str | None
    expiry: str | None
    strike_decimal: str | None
    tick_size_decimal: str | None
    lot_size: int
    instrument_type: str
    segment: str
    exchange: str
    source_fields_hash: str


@dataclass(frozen=True)
class NativeReferenceResult:
    classification: str
    reason_code: str
    decoded_payload_hash: str | None = None
    rows: tuple[ReferenceRow, ...] = ()
    failure_row_ordinal: int | None = None


class DecodeRejected(ValueError):
    pass


def decode_content(raw: bytes, headers: tuple[tuple[str, str], ...]) -> bytes:
    """Single gzip member only; reject trailing bytes and concatenated members.

    Never use unbounded flush/decompress or return a salvaged decoded prefix.
    """
    if not isinstance(raw, bytes):
        raise TypeError("EXACT_BYTES_REQUIRED")
    if len(raw) > MAX_ENCODED_BYTES:
        raise DecodeRejected("ENCODED_BYTE_LIMIT")
    encodings = [v for k, v in headers if k.lower() == "content-encoding"]
    types = [v for k, v in headers if k.lower() == "content-type"]
    if len(encodings) > 1 or len(types) > 1:
        raise DecodeRejected("AMBIGUOUS_CONTENT_HEADERS")
    if types:
        media = types[0].split(";", 1)[0].strip().lower()
        if media not in {"text/csv", "application/csv", "text/plain", "application/octet-stream"}:
            raise DecodeRejected("UNSUPPORTED_MEDIA_TYPE")
        for parameter in types[0].split(";")[1:]:
            key, sep, value = parameter.strip().partition("=")
            if key.lower() == "charset" and (
                not sep or value.strip(' "').lower() not in {"utf-8", "utf8", "us-ascii"}
            ):
                raise DecodeRejected("UNSUPPORTED_CHARSET")
    encoding = encodings[0].strip().lower() if encodings else "identity"
    if encoding == "identity":
        if len(raw) > MAX_DECODED_BYTES:
            raise DecodeRejected("DECODED_BYTE_LIMIT")
        return raw
    if encoding != "gzip":
        raise DecodeRejected("UNSUPPORTED_CONTENT_ENCODING")
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        decoded = decoder.decompress(raw, MAX_DECODED_BYTES + 1)
    except zlib.error:
        raise DecodeRejected("INVALID_GZIP") from None
    if len(decoded) > MAX_DECODED_BYTES or decoder.unconsumed_tail:
        raise DecodeRejected("DECODED_BYTE_LIMIT")
    if not decoder.eof:
        raise DecodeRejected("TRUNCATED_GZIP")
    if decoder.unused_data:
        raise DecodeRejected("GZIP_TRAILING_DATA")
    return decoded


def _integer(raw: str, maximum: int, *, positive: bool = False) -> int:
    if not re.fullmatch(r"[0-9]{1,20}", raw):
        raise DecodeRejected("INVALID_INTEGER")
    number = int(raw)
    if number > maximum or (positive and not number):
        raise DecodeRejected("INTEGER_RANGE")
    return number


def _decimal(raw: str) -> str | None:
    if raw == "":
        return None
    if len(raw) > 64 or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", raw):
        raise DecodeRejected("INVALID_DECIMAL")
    return raw


def parse_native_csv(decoded: bytes) -> NativeReferenceResult:
    if len(decoded) > MAX_DECODED_BYTES:
        return NativeReferenceResult("quarantine", "DECODED_BYTE_LIMIT")
    hashed = digest(decoded)
    rows: list[ReferenceRow] = []
    ordinal: int | None = None
    try:
        text = decoded.decode("utf-8-sig")
        if "\x00" in text:
            raise DecodeRejected("NUL_IN_CSV")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader, None)
        if header is None or tuple(s.strip() for s in header) != COLUMNS:
            raise DecodeRejected("UNSUPPORTED_CSV_HEADER")
        for ordinal, row in enumerate(reader):
            if ordinal >= MAX_ROWS:
                raise DecodeRejected("ROW_COUNT_LIMIT")
            if len(row) != len(COLUMNS):
                raise DecodeRejected("CSV_COLUMN_COUNT")
            if any(len(s) > 4096 for s in row):
                raise DecodeRejected("CSV_FIELD_LIMIT")
            fields = dict(zip(COLUMNS, row, strict=True))
            for key in ("tradingsymbol", "instrument_type", "segment", "exchange"):
                value = fields[key]
                if not value or value != value.strip() or any(ord(c) < 32 for c in value):
                    raise DecodeRejected("INVALID_IDENTIFIER")
            token = _integer(fields["instrument_token"], 2**32 - 1, positive=True)
            _integer(fields["exchange_token"], 2**32 - 1)
            lot = _integer(fields["lot_size"], 2**63 - 1)
            expiry = fields["expiry"] or None
            if expiry is not None:
                if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", expiry):
                    raise DecodeRejected("INVALID_EXPIRY")
                try:
                    date.fromisoformat(expiry)
                except ValueError:
                    raise DecodeRejected("INVALID_EXPIRY") from None
            if fields["instrument_type"] in {"CE", "PE", "FUT"} and expiry is None:
                raise DecodeRejected("MISSING_DERIVATIVE_EXPIRY")
            strike = _decimal(fields["strike"])
            if fields["instrument_type"] in {"CE", "PE"} and strike is None:
                raise DecodeRejected("MISSING_OPTION_STRIKE")
            rows.append(
                ReferenceRow(
                    ordinal,
                    token,
                    fields["exchange_token"],
                    fields["tradingsymbol"],
                    fields["name"],
                    _decimal(fields["last_price"]),
                    expiry,
                    strike,
                    _decimal(fields["tick_size"]),
                    lot,
                    fields["instrument_type"],
                    fields["segment"],
                    fields["exchange"],
                    digest(canonical(row).encode()),
                )
            )
        if not rows:
            raise DecodeRejected("EMPTY_REFERENCE_SNAPSHOT")
    except DecodeRejected as error:
        return NativeReferenceResult("quarantine", str(error), hashed, (), ordinal)
    except UnicodeError:
        return NativeReferenceResult("quarantine", "INVALID_CSV_UTF8", hashed)
    except csv.Error:
        return NativeReferenceResult("quarantine", "MALFORMED_CSV", hashed, (), ordinal)
    return NativeReferenceResult("normalized", "NORMALIZED", hashed, tuple(rows))


def normalize_native_content(
    raw: bytes,
    headers: tuple[tuple[str, str], ...],
) -> NativeReferenceResult:
    try:
        decoded = decode_content(raw, headers)
    except DecodeRejected as error:
        return NativeReferenceResult("quarantine", str(error))
    return parse_native_csv(decoded)
