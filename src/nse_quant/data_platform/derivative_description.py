"""Pure source-pinned derivative descriptions, never canonical instrument authority."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

VERSION = "provider-derivative-description@1"
MAX_ROW_BYTES = 65536
MAX_DESCRIPTION_BYTES = 131072
DEFINITION = (
    VERSION,
    "NFO/NFO-OPT/CE|PE and NFO/NFO-FUT/FUT only",
    "provider_name is an unverified provider label, never canonical underlying identity",
    "no trading-symbol inference; date-only expiry is not a validity instant",
    "exact decimal normalization; token/lot/tick/symbol changes retained in description identity",
    "description-key equality is not canonical contract equivalence",
    "no provenance, availability, historical validity, publication or decision authority",
)
FIELDS = frozenset(
    {
        "row_ordinal",
        "instrument_token",
        "exchange_token",
        "tradingsymbol",
        "provider_name",
        "last_price_decimal",
        "expiry",
        "strike_decimal",
        "tick_size_decimal",
        "lot_size",
        "instrument_type",
        "segment",
        "exchange",
        "source_fields_hash",
    }
)


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


DEFINITION_FINGERPRINT = digest(DEFINITION)


def _pin(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _json(text: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_DESCRIPTION_JSON_KEY")
            result[key] = value
        return result

    def invalid(_value: str) -> Any:
        raise ValueError("NONFINITE_DESCRIPTION_JSON")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


def _decimal(value: object) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) > 64
        or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value)
    ):
        raise ValueError("INVALID_DESCRIPTION_DECIMAL")
    whole, _, fraction = value.partition(".")
    whole = whole.lstrip("0") or "0"
    fraction = fraction.rstrip("0")
    return whole + ("." + fraction if fraction else "")


@dataclass(frozen=True)
class DerivativeDescription:
    description_id: str
    version: str
    definition_fingerprint: str
    assessment_revision_id: str
    frozen_row_json: str
    status: str
    reason_codes: tuple[str, ...]
    provider_description_key: str | None = None
    normalized_strike: str | None = None
    normalized_tick_size: str | None = None
    canonical_contract_id: None = None
    canonical_underlying_id: None = None
    provenance_verified: bool = False
    historical_validity_asserted: bool = False
    availability_evidence_verified: bool = False
    publication_asserted: bool = False
    decision_eligibility_asserted: bool = False


def describe_derivative_row(
    *,
    assessment_revision_id: str,
    frozen_row_json: str,
) -> DerivativeDescription:
    """Validate a supplied typed-row projection; no DB/source authenticity claim.

    Exact full native ReferenceRow fields are frozen, including unused fields.
    A syntactically valid fake row remains fake: this pure API is not verification.
    Unsupported/incomplete domain observations stay explicit; malformed schema raises.
    """
    if not _pin(assessment_revision_id):
        raise ValueError("EXACT_DESCRIPTION_ASSESSMENT_PIN_REQUIRED")
    if not isinstance(frozen_row_json, str) or len(frozen_row_json.encode()) > MAX_ROW_BYTES:
        raise ValueError("DESCRIPTION_ROW_BYTE_LIMIT")
    row = _json(frozen_row_json)
    if not isinstance(row, dict) or set(row) != FIELDS or canonical(row) != frozen_row_json:
        raise ValueError("DESCRIPTION_ROW_SCHEMA_OR_CANONICAL_MISMATCH")
    if (
        type(row["row_ordinal"]) is not int
        or not 0 <= row["row_ordinal"] < 200000
        or type(row["instrument_token"]) is not int
        or not 0 < row["instrument_token"] < 2**32
        or type(row["lot_size"]) is not int
        or not 0 <= row["lot_size"] < 2**63
        or not _pin(row["source_fields_hash"])
    ):
        raise ValueError("DESCRIPTION_ROW_TYPES_OR_PINS_INVALID")
    for field in (
        "exchange_token",
        "tradingsymbol",
        "provider_name",
        "instrument_type",
        "segment",
        "exchange",
    ):
        text = row[field]
        if not isinstance(text, str) or len(text) > 4096 or any(ord(c) < 32 for c in text):
            raise ValueError("DESCRIPTION_TEXT_SCHEMA_INVALID")
    if (
        not re.fullmatch(r"[0-9]{1,20}", row["exchange_token"])
        or int(row["exchange_token"]) >= 2**32
    ):
        raise ValueError("DESCRIPTION_EXCHANGE_TOKEN_INVALID")
    strike = _decimal(row["strike_decimal"])
    tick = _decimal(row["tick_size_decimal"])
    _decimal(row["last_price_decimal"])
    expiry = row["expiry"]
    if expiry is not None:
        if not isinstance(expiry, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", expiry):
            raise ValueError("DESCRIPTION_EXPIRY_SCHEMA_INVALID")
        date.fromisoformat(expiry)
    status = "described"
    reasons: tuple[str, ...] = ("PROVIDER_LABELLED_DERIVATIVE_DESCRIPTION_ONLY",)
    key = None
    triple = (row["exchange"], row["segment"], row["instrument_type"])
    supported = triple in {
        ("NFO", "NFO-OPT", "CE"),
        ("NFO", "NFO-OPT", "PE"),
        ("NFO", "NFO-FUT", "FUT"),
    }
    if not supported:
        status, reasons = "unsupported", ("UNSUPPORTED_VENUE_SEGMENT_OR_TYPE",)
    elif not re.fullmatch(r"[A-Z0-9][A-Z0-9&._-]{0,63}", row["provider_name"]):
        status, reasons = "unresolved", ("EXPLICIT_SUPPORTED_PROVIDER_LABEL_REQUIRED",)
    elif not row["tradingsymbol"] or row["tradingsymbol"] != row["tradingsymbol"].strip():
        status, reasons = "unresolved", ("PROVIDER_TRADING_SYMBOL_REQUIRED",)
    elif expiry is None or row["lot_size"] == 0 or tick in {None, "0"}:
        status, reasons = "unresolved", ("INCOMPLETE_DERIVATIVE_TERMS",)
    elif row["instrument_type"] in {"CE", "PE"} and strike in {None, "0"}:
        status, reasons = "unresolved", ("POSITIVE_OPTION_STRIKE_REQUIRED",)
    elif row["instrument_type"] == "FUT" and strike not in {None, "0"}:
        status, reasons = "inconsistent", ("NONZERO_FUTURE_STRIKE_OBSERVED",)
    else:
        key = digest(
            [
                VERSION,
                *triple,
                row["provider_name"],
                expiry,
                strike if row["instrument_type"] != "FUT" else None,
            ]
        )
    value = DerivativeDescription(
        "",
        VERSION,
        DEFINITION_FINGERPRINT,
        assessment_revision_id,
        frozen_row_json,
        status,
        reasons,
        key,
        strike,
        tick,
    )
    payload = asdict(value)
    del payload["description_id"]
    return DerivativeDescription(**dict(payload, description_id=digest(payload)))


def encode_derivative_description(value: DerivativeDescription) -> bytes:
    expected = describe_derivative_row(
        assessment_revision_id=value.assessment_revision_id, frozen_row_json=value.frozen_row_json
    )
    if canonical(asdict(value)) != canonical(asdict(expected)):
        raise ValueError("DERIVATIVE_DESCRIPTION_RESULT_MISMATCH")
    raw = canonical(asdict(value)).encode()
    if len(raw) > MAX_DESCRIPTION_BYTES:
        raise ValueError("DESCRIPTION_BYTE_LIMIT")
    return raw


def decode_derivative_description(
    raw: bytes, *, expected_description_id: str
) -> DerivativeDescription:
    """Strict offline consistency only; no provenance/identity authority restoration."""
    if not isinstance(raw, bytes) or len(raw) > MAX_DESCRIPTION_BYTES:
        raise ValueError("DESCRIPTION_BYTE_LIMIT")
    value = _json(raw.decode("utf-8"))
    if not isinstance(value, dict) or set(value) != set(DerivativeDescription.__dataclass_fields__):
        raise ValueError("DESCRIPTION_SCHEMA_MISMATCH")
    result = describe_derivative_row(
        assessment_revision_id=value["assessment_revision_id"],
        frozen_row_json=value["frozen_row_json"],
    )
    if not _pin(expected_description_id) or result.description_id != expected_description_id:
        raise ValueError("DESCRIPTION_ID_MISMATCH")
    if encode_derivative_description(result) != raw:
        raise ValueError("DESCRIPTION_RESULT_OR_CANONICAL_MISMATCH")
    return result
