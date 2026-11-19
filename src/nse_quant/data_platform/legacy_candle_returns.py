"""Exact adjacent-retained candle changes/returns; not regular-grid market returns."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, datetime
from fractions import Fraction
from typing import Any

VERSION = "legacy-stored-candle-returns@1"
MAX_ROWS = 16000
MAX_ROW_BYTES = 65536
MAX_TOTAL_BYTES = 33554432


def _close(value: object) -> Fraction | None:
    if value is None:
        return None
    if type(value) is not str or len(value) > 32:
        raise ValueError("EXACT_STORED_CLOSE_HEX_REQUIRED")
    number = float.fromhex(value)
    if not math.isfinite(number) or number.hex() != value:
        raise ValueError("EXACT_FINITE_CANONICAL_STORED_CLOSE_REQUIRED")
    return Fraction(number)


def _ratio(value: Fraction | None) -> dict[str, str] | None:
    if value is None:
        return None
    return dict(numerator=str(value.numerator), denominator=str(value.denominator))


def adjacent_candle_features(fields: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    """Pure bounded kernel; native store must validate complete actual source records.

    Group by retained token/interval; sort stored UTC instants; emit original input order.
    Missing/zero operands never cause bridging. No bar-completeness/session inference.
    """
    if type(fields) is not tuple or not 1 <= len(fields) <= MAX_ROWS:
        raise ValueError("COMPLETE_CANDLE_SERIES_ROW_BOUND")
    groups: dict[tuple[str, str], list[tuple[datetime, int]]] = defaultdict(list)
    closes: list[Fraction | None] = []
    for ordinal, row in enumerate(fields):
        if type(row) is not dict:
            raise ValueError("CANDLE_FIELDS_REQUIRED")
        token, interval, symbol, ts = (
            row[k] for k in ("instrument_token", "interval", "symbol", "ts")
        )
        if (
            type(token) is not str
            or len(token) > 20
            or str(int(token)) != token
            or not -(2**63) <= int(token) < 2**63
            or type(interval) is not str
            or len(interval.encode()) > 65536
            or symbol is not None
            and (type(symbol) is not str or len(symbol.encode()) > 65536)
            or type(ts) is not str
            or len(ts) > 64
        ):
            raise ValueError("CANDLE_SERIES_STORED_KEY_CONTRACT")
        at = datetime.fromisoformat(ts)
        if at.tzinfo is None or at.utcoffset() is None or at.astimezone(UTC).isoformat() != ts:
            raise ValueError("CANONICAL_STORED_UTC_CANDLE_TIME_REQUIRED")
        closes.append(_close(row["close"]))
        groups[(token, interval)].append((at, ordinal))
    output: dict[int, dict[str, Any]] = {}
    for (_token, interval), members in groups.items():
        members.sort()
        if len({at for at, _ordinal in members}) != len(members):
            raise ValueError("DUPLICATE_CANDLE_SERIES_INSTANT_NO_WINNER")
        prior: int | None = None
        prior_at: datetime | None = None
        for at, ordinal in members:
            row = fields[ordinal]
            value = closes[ordinal]
            flags: list[str] = []
            if not interval:
                flags.append("INTERVAL_UNKNOWN")
            if row["symbol"] is None or row["symbol"] == "":
                flags.append("SYMBOL_UNKNOWN")
            if value is None:
                flags.append("CURRENT_CLOSE_MISSING")
            elif value <= 0:
                flags.append("CURRENT_CLOSE_NONPOSITIVE")
            change = result = None
            elapsed = None
            if prior is None:
                flags.append("NO_PREDECESSOR_IN_RETAINED_SET")
            else:
                previous = closes[prior]
                delta = at - prior_at if prior_at is not None else None
                assert delta is not None
                elapsed = str((delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds)
                if previous is None:
                    flags.append("PREVIOUS_CLOSE_MISSING")
                elif previous <= 0:
                    flags.append("PREVIOUS_CLOSE_NONPOSITIVE")
                if row["symbol"] != fields[prior]["symbol"]:
                    flags.append("SYMBOL_CHANGED_NO_BINDING")
                if value is not None and previous is not None:
                    change = value - previous
                    if (
                        previous != 0
                        and interval
                        and row["symbol"] not in (None, "")
                        and row["symbol"] == fields[prior]["symbol"]
                    ):
                        result = change / previous
            output[ordinal] = dict(
                predecessor_ordinal=prior,
                elapsed_stored_microseconds=elapsed,
                close_change=_ratio(change),
                simple_return=_ratio(result),
                return_status="UNAVAILABLE" if result is None else "COMPUTED_RESEARCH",
                quality_flags=flags,
            )
            prior, prior_at = ordinal, at
    return tuple(output[i] for i in range(len(fields)))


def derive_return_records(
    records: tuple[bytes, ...], *, source_build_id: str, source_recording_fingerprint: str
) -> tuple[bytes, ...]:
    """Complete content recomputation; not an independent upstream audit attestation."""
    from nse_quant.data_platform import legacy_market_gold as gold

    if not gold.pin(source_build_id) or not gold.pin(source_recording_fingerprint):
        raise ValueError("EXACT_RETURN_SOURCE_PINS_REQUIRED")
    docs = gold.validate_source_records(records)
    if any(d["source_table"] != "spot_candles" for d in docs):
        raise ValueError("COMPLETE_SPOT_CANDLES_SOURCE_REQUIRED")
    features = adjacent_candle_features(tuple(d["stored_fields"] for d in docs))
    result: list[bytes] = []
    total = 0
    for ordinal, (raw, doc, values) in enumerate(zip(records, docs, features, strict=True)):
        previous = values["predecessor_ordinal"]
        body = dict(
            version=VERSION,
            source_build_id=source_build_id,
            source_recording_fingerprint=source_recording_fingerprint,
            source_ordinal=ordinal,
            source_record_id=gold.sha(raw),
            predecessor_source_record_id=None if previous is None else gold.sha(records[previous]),
            source_pins=doc["source_pins"],
            source_observation_id=doc["source_observation_id"],
            partition_index=doc["partition_index"],
            event_ts=doc["stored_fields"]["ts"],
            retained_instrument_token=doc["stored_fields"]["instrument_token"],
            retained_interval_sha256=gold.sha(gold.canonical(doc["stored_fields"]["interval"])),
            values=values,
            semantics="ADJACENT_RETAINED_STORED_CLOSE_NOT_REGULAR_GRID_RETURN",
            coverage_verified=False,
            canonical_contract_id=None,
            availability_verified=False,
            economic_validity_verified=False,
            published_at=None,
            publication_asserted=False,
            decision_eligibility_asserted=False,
        )
        encoded = gold.canonical(body)
        total += len(encoded)
        if len(encoded) > MAX_ROW_BYTES or total > MAX_TOTAL_BYTES:
            raise ValueError("CANDLE_RETURN_OUTPUT_BYTE_BOUND")
        result.append(encoded)
    return tuple(result)
