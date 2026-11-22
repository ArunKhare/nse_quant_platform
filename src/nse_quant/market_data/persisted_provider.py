"""Run-bound, read-only reconstruction of persisted operational quotes."""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field

from nse_quant.core.models import ChainSnapshot, Instrument, OptionQuote, OptionType

if TYPE_CHECKING:
    from nse_quant.persistence.duckdb_store import DuckDBStore

RECONSTRUCTION_VERSION = "persisted_reconstruction_v1"


class PersistedSnapshotError(ValueError):
    """Selected persisted batch violates its reconstruction contract."""


class PersistedOptionQuote(OptionQuote):
    # Unlike live quotes, historical rows may have no known receipt timestamp.
    received_at: datetime | None = None  # type: ignore[assignment]


class PersistedChainSnapshot(ChainSnapshot):
    reconstruction_version: str = RECONSTRUCTION_VERSION
    timestamp_provenance: dict[int, dict[str, str]] = Field(default_factory=dict)
    decision_eligibility_asserted: Literal[False] = False


def _object(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError) as exc:
        raise PersistedSnapshotError("invalid_json_payload") from exc
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise PersistedSnapshotError("json_object_required")
    return parsed


def _timestamp(value: Any, field: str) -> datetime | None:
    if value is None:
        return None
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise PersistedSnapshotError(f"invalid_timestamp:{field}") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise PersistedSnapshotError(f"timezone_required:{field}")
    return result.astimezone(UTC)


class PersistedChainSnapshotProvider:
    """Keep the combined-snapshot API while reconstructing one exact batch.

    Header-first/latest-complete selection and the legacy row-derived fallback
    remain. This reader does not assert horizon coverage or trade eligibility.
    Store construction and process ownership remain the caller's responsibility.
    """

    def __init__(
        self,
        store: DuckDBStore,
        *,
        underlying: str,
        required_expiries: int = 2,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if isinstance(required_expiries, bool) or not isinstance(required_expiries, int) or required_expiries < 1:
            raise ValueError("required_expiries must be a positive integer")
        self.store = store
        self.underlying = underlying
        self.required_expiries = required_expiries
        self.clock = clock or (lambda: datetime.now(UTC))

    def get_chain_snapshot(self) -> ChainSnapshot:
        snapshots = self.get_chain_snapshots()
        if not snapshots:
            raise ValueError("No complete persisted option-chain snapshots available")
        return snapshots[0]

    def get_chain_snapshots(self) -> list[ChainSnapshot]:
        now = _timestamp(self.clock(), "clock")
        if now is None:
            raise PersistedSnapshotError("clock_required")
        max_age = float(self.store.settings.runtime.stale_seconds)
        if not math.isfinite(max_age) or max_age <= 0:
            raise PersistedSnapshotError("invalid_freshness_limit")
        cutoff = now - timedelta(seconds=int(max_age))
        header = self.store.conn.execute(
            """SELECT ts, run_id, spot, expiry_count, quote_count, completeness
               FROM option_chain_snapshots
               WHERE underlying = ? AND complete = TRUE AND expiry_count >= ? AND ts >= ?
               ORDER BY ts DESC LIMIT 1""",
            [self.underlying, self.required_expiries, cutoff],
        ).fetchone()
        if header is not None:
            ts, run_id, spot = header[:3]
        else:
            candidates = self.store.conn.execute(
                """WITH per_expiry AS (
                       SELECT ts, run_id, expiry
                       FROM option_stream WHERE underlying = ? AND ts >= ?
                       GROUP BY ts, run_id, expiry
                       HAVING COUNT(iv) > 0 AND COUNT(CASE WHEN delta IS NOT NULL
                         AND gamma IS NOT NULL AND vega IS NOT NULL AND theta IS NOT NULL THEN 1 END) > 0
                   )
                   SELECT ts, run_id FROM per_expiry GROUP BY ts, run_id
                   HAVING COUNT(*) >= ? ORDER BY ts DESC, run_id LIMIT 2""",
                [self.underlying, cutoff, self.required_expiries],
            ).fetchall()
            if not candidates:
                return []
            if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
                raise PersistedSnapshotError("ambiguous_legacy_batch")
            ts, run_id = candidates[0]
            spot = None
        if not run_id or ts > now:
            raise PersistedSnapshotError("invalid_batch_identity_or_future_timestamp")
        rows = self.store.conn.execute(
            """SELECT expiry, instrument_token, tradingsymbol, strike, option_type, lot_size,
                      spot, ltp, bid, ask, volume, oi, iv, delta, gamma, vega, theta, payload_json
               FROM option_stream WHERE underlying = ? AND ts = ? AND run_id = ?
               ORDER BY expiry, strike, option_type""",
            [self.underlying, ts, run_id],
        ).fetchall()
        if not rows:
            raise PersistedSnapshotError("selected_batch_has_no_rows")
        if spot is None:
            spot = rows[0][6]
        if spot is None or not math.isfinite(spot) or spot <= 0:
            raise PersistedSnapshotError("invalid_spot")
        counts = Counter(row[0].isoformat() for row in rows)
        if len(counts) < self.required_expiries or len({row[1] for row in rows}) != len(rows):
            raise PersistedSnapshotError("invalid_batch_expiries_or_duplicate_tokens")
        if header is not None:
            manifest = _object(header[5])
            if header[3] != len(counts) or header[4] != len(rows) or set(manifest) != set(counts):
                raise PersistedSnapshotError("summary_row_manifest_mismatch")
            for expiry, count in counts.items():
                entry = manifest[expiry]
                if not isinstance(entry, dict) or entry.get("quote_count") != count:
                    raise PersistedSnapshotError("summary_row_manifest_mismatch")
        quotes: list[OptionQuote] = []
        provenance: dict[int, dict[str, str]] = {}
        for row in rows:
            if row[6] != spot:
                raise PersistedSnapshotError("inconsistent_batch_spot")
            for value in (row[3], *row[7:17]):
                if value is not None and not math.isfinite(value):
                    raise PersistedSnapshotError("non_finite_quote_value")
            payload = _object(row[17])
            token = int(row[1])
            if "instrument_token" in payload and payload["instrument_token"] != token:
                raise PersistedSnapshotError("payload_instrument_mismatch")
            times = {name: _timestamp(payload.get(name), name)
                     for name in ("exchange_ts", "trade_ts", "received_at")}
            provenance[token] = {name: "persisted_payload" if value is not None else "missing"
                                 for name, value in times.items()}
            instrument = Instrument(
                underlying=self.underlying, expiry=row[0], instrument_token=token,
                tradingsymbol=row[2], strike=row[3], option_type=OptionType(row[4]), lot_size=row[5],
            )
            quotes.append(PersistedOptionQuote(
                instrument=instrument, instrument_token=token,
                ltp=row[7], bid=row[8], ask=row[9], volume=row[10], oi=row[11], iv=row[12],
                delta=row[13], gamma=row[14], vega=row[15], theta=row[16], **times,
            ))
        return [PersistedChainSnapshot(
            run_id=run_id, ts=ts, underlying=self.underlying, spot=spot,
            expiry=min(quote.instrument.expiry for quote in quotes), quotes=quotes,
            timestamp_provenance=provenance,
        )]
