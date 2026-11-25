"""Content-pinned EOD IV30 research history; no Gold or eligibility authority.

NSE file origin is a supplied provenance claim, not authenticated by a checksum.
No intraday last-observation substitution or cross-source history splicing.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from datetime import date, datetime
from typing import Any, TypedDict

VERSION = "s2-retained-eod-iv30-history@1"
MAX_RAW = 2 * 1024 * 1024
MAX_ROWS = 10000
MAX_BUNDLE = 5 * 1024 * 1024


class HistoryRow(TypedDict):
    trade_date: str
    iv30: float
    value_percent: float
    available_at: str
    raw_row_ordinal: int


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _time(text: str) -> datetime:
    value = datetime.fromisoformat(text)
    if value.utcoffset() is None:
        raise ValueError("AWARE_HISTORY_CLOCK_REQUIRED")
    return value


def build_history(
    *,
    raw_csv: bytes,
    expected_raw_sha256: str,
    source_reference: str,
    received_at: str,
    as_of: str,
    date_column: str,
    close_column: str,
    date_format: str = "%Y-%m-%d",
) -> bytes:
    """Parse explicitly mapped official-file closes, preserving original bytes.

    Received-at is conservative availability for ALL rows, never exchange date.
    Caller must retain authentic acquisition evidence separately; no authenticity
    or historical point-in-time availability is inferred from these input rows.
    """
    if type(raw_csv) is not bytes or not 0 < len(raw_csv) <= MAX_RAW or sha(raw_csv) != expected_raw_sha256:
        raise ValueError("EOD_RAW_PIN_OR_BYTE_BOUND")
    if not isinstance(source_reference, str) or not source_reference.strip():
        raise ValueError("EOD_SOURCE_REFERENCE_REQUIRED")
    received, cutoff = _time(received_at), _time(as_of)
    if received > cutoff:
        raise ValueError("EOD_NOT_YET_AVAILABLE")
    if date_column == close_column:
        raise ValueError("DISTINCT_EOD_COLUMN_MAPPING_REQUIRED")
    reader = csv.DictReader(io.StringIO(raw_csv.decode("utf-8-sig"), newline=""))
    if (
        not reader.fieldnames
        or len(set(reader.fieldnames)) != len(reader.fieldnames)
        or date_column not in reader.fieldnames
        or close_column not in reader.fieldnames
    ):
        raise ValueError("EOD_HEADER_MAPPING_MISMATCH")
    rows: list[HistoryRow] = []
    seen = set()
    for ordinal, row in enumerate(reader):
        if ordinal >= MAX_ROWS or None in row:
            raise ValueError("EOD_ROW_OR_COLUMN_BOUND")
        day = datetime.strptime(row[date_column].strip(), date_format).date()
        value = float(row[close_column])
        if not math.isfinite(value) or value <= 0 or day in seen or day >= cutoff.date():
            raise ValueError("EOD_INVALID_DUPLICATE_OR_NOT_COMPLETED_DATE")
        seen.add(day)
        rows.append(
            dict(
                trade_date=day.isoformat(),
                iv30=value / 100,
                value_percent=value,
                available_at=received_at,
                raw_row_ordinal=ordinal,
            )
        )
    if not rows:
        raise ValueError("EOD_EMPTY_HISTORY")
    rows.sort(key=lambda row: row["trade_date"])
    request = dict(
        raw_csv_hex=raw_csv.hex(),
        expected_raw_sha256=expected_raw_sha256,
        source_reference=source_reference,
        received_at=received_at,
        as_of=as_of,
        date_column=date_column,
        close_column=close_column,
        date_format=date_format,
    )
    result = canonical(
        dict(
            version=VERSION,
            request=request,
            rows=rows,
            iv30_source="india_vix",
            sampling="supplied_eod_file_close",
            acquisition_authenticity_verified=False,
            historical_availability_asserted=False,
            decision_eligibility_asserted=False,
        )
    )
    if len(result) > MAX_BUNDLE:
        raise ValueError("EOD_HISTORY_BYTE_BOUND")
    return result


def replay_history(raw: bytes, *, expected_sha256: str) -> dict[str, Any]:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BUNDLE or sha(raw) != expected_sha256:
        raise ValueError("EOD_HISTORY_PIN_OR_BYTE_BOUND")
    doc = json.loads(raw)
    if set(doc) != {
        "version",
        "request",
        "rows",
        "iv30_source",
        "sampling",
        "acquisition_authenticity_verified",
        "historical_availability_asserted",
        "decision_eligibility_asserted",
    }:
        raise ValueError("EOD_HISTORY_SHAPE_MISMATCH")
    request = dict(doc["request"])
    request["raw_csv"] = bytes.fromhex(request.pop("raw_csv_hex"))
    if build_history(**request) != raw:
        raise ValueError("EOD_HISTORY_REPLAY_MISMATCH")
    return doc


def iv_percentile(
    raw: bytes, *, expected_sha256: str, trade_date: str, lookback: int = 252, minimum_history: int = 120
) -> float:
    """Strict-less empirical rank against prior EOD rows; no future rows used.

    History sufficiency means supplied observations, not exchange-session coverage.
    This helper does not certify a calibrated IV-state classifier.
    """
    if type(lookback) is not int or type(minimum_history) is not int or not 1 <= minimum_history <= lookback <= 252:
        raise ValueError("BOUNDED_HISTORY_WINDOW_REQUIRED")
    rows = replay_history(raw, expected_sha256=expected_sha256)["rows"]
    date.fromisoformat(trade_date)
    current = [row for row in rows if row["trade_date"] == trade_date]
    prior = [row["iv30"] for row in rows if row["trade_date"] < trade_date][-lookback:]
    if len(current) != 1 or len(prior) < minimum_history:
        raise ValueError("INSUFFICIENT_DAILY_IV_HISTORY")
    return 100 * sum(value < current[0]["iv30"] for value in prior) / len(prior)
