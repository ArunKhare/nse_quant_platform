"""Migrate legacy option_stream rows into Medallion Bronze.

Safety:
- Historical import only.
- Paper-only; no trading, live acquisition, or production cutover.
- Idempotent by canonical snapshot identity.
- Does not mutate or delete option_stream source rows.
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
from typing import Any

from nse_quant.data_platform.option_stream_history_migration import (
    OptionStreamSnapshot,
    migrate_option_stream_snapshot,
)
from nse_quant.persistence.duckdb_store import DuckDBStore

MIGRATION_LEDGER_SQL = """
CREATE SCHEMA IF NOT EXISTS medallion_migration;
CREATE TABLE IF NOT EXISTS medallion_migration.option_stream_migration (
    underlying VARCHAR NOT NULL,
    trading_date DATE NOT NULL,
    snapshot_ts TIMESTAMPTZ NOT NULL,
    source_label VARCHAR NOT NULL,
    snapshot_id VARCHAR NOT NULL,
    bronze_capture_event_id VARCHAR,
    bronze_envelope_hash VARCHAR,
    bronze_recording_fingerprint VARCHAR,
    status VARCHAR NOT NULL,
    error_code VARCHAR,
    migrated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (underlying, trading_date, snapshot_ts, source_label)
);
"""


def ensure_ledger(store: DuckDBStore) -> None:
    store.conn.execute(MIGRATION_LEDGER_SQL)


def already_migrated(store: DuckDBStore, snapshot: OptionStreamSnapshot) -> bool:
    row = store.conn.execute(
        """
        SELECT 1
        FROM medallion_migration.option_stream_migration
        WHERE underlying = ?
          AND trading_date = ?
          AND snapshot_ts = ?
          AND source_label = ?
          AND status = 'SUCCEEDED'
        """,
        [
            snapshot.underlying,
            snapshot.trading_date,
            snapshot.snapshot_ts,
            snapshot.source_label,
        ],
    ).fetchone()
    return row is not None


def record_result(
    store: DuckDBStore,
    snapshot: OptionStreamSnapshot,
    *,
    status: str,
    result: dict[str, Any] | None = None,
    error_code: str | None = None,
) -> None:
    store.conn.execute(
        """
        INSERT OR REPLACE INTO medallion_migration.option_stream_migration (
            underlying, trading_date, snapshot_ts, source_label, snapshot_id,
            bronze_capture_event_id, bronze_envelope_hash,
            bronze_recording_fingerprint, status, error_code, migrated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            snapshot.underlying,
            snapshot.trading_date,
            snapshot.snapshot_ts,
            snapshot.source_label,
            snapshot.snapshot_id,
            (result or {}).get("capture_event_id"),
            (result or {}).get("envelope_hash"),
            (result or {}).get("recording_fingerprint"),
            status,
            error_code,
            datetime.now(UTC),
        ],
    )


def load_snapshots(
    store: DuckDBStore,
    *,
    underlying: str,
    start_date: date,
    end_date: date,
) -> list[OptionStreamSnapshot]:
    rows = store.conn.execute(
        """
        SELECT ts, underlying, expiry, strike, option_type, tradingsymbol,
               instrument_token, lot_size, spot, ltp, bid, ask, volume, oi,
               iv, delta, gamma, vega, theta, quote_status, payload_json
        FROM option_stream
        WHERE underlying = ?
          AND CAST(ts AS DATE) BETWEEN ? AND ?
        ORDER BY ts, instrument_token, strike, option_type
        """,
        [underlying, start_date, end_date],
    ).fetchall()

    columns = [
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
    ]

    grouped: dict[tuple[str, date, datetime], list[dict[str, Any]]] = {}
    for row in rows:
        record = dict(zip(columns, row, strict=True))
        ts = record["ts"]
        if not isinstance(ts, datetime):
            raise ValueError("option_stream.ts must be a datetime")
        trading_date = ts.date()
        key = (underlying, trading_date, ts)
        grouped.setdefault(key, []).append(record)

    snapshots: list[OptionStreamSnapshot] = []
    for (symbol, trading_date, ts), records in sorted(grouped.items()):
        snapshots.append(
            OptionStreamSnapshot(
                underlying=symbol,
                trading_date=trading_date,
                snapshot_ts=ts,
                rows=tuple(records),
            )
        )
    return snapshots


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--underlying", default="NIFTY")
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    parser.add_argument("--actor-id", default="migration-operator")
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--mode", choices=["dry-run", "apply"], default="dry-run")
    args = parser.parse_args()

    if args.start_date > args.end_date:
        raise ValueError("--start-date must be <= --end-date")

    store = DuckDBStore()
    try:
        ensure_ledger(store)
        snapshots = load_snapshots(
            store,
            underlying=args.underlying,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        print(f"Discovered {len(snapshots)} option-stream snapshots")

        succeeded = skipped = failed = 0
        for snapshot in snapshots:
            if already_migrated(store, snapshot):
                skipped += 1
                print(f"SKIP {snapshot.snapshot_ts.isoformat()} already migrated")
                continue

            if args.mode == "dry-run":
                print(
                    f"DRY-RUN {snapshot.snapshot_ts.isoformat()} "
                    f"rows={len(snapshot.rows)} snapshot_id={snapshot.snapshot_id}"
                )
                continue

            try:
                result = migrate_option_stream_snapshot(
                    store.conn,
                    snapshot,
                    actor_id=args.actor_id,
                    code_revision=args.code_revision,
                )
                record_result(store, snapshot, status="SUCCEEDED", result=result)
                succeeded += 1
                print(f"MIGRATED {snapshot.snapshot_ts.isoformat()} capture_event_id={result['capture_event_id']}")
            except Exception as exc:
                failed += 1
                record_result(
                    store,
                    snapshot,
                    status="FAILED",
                    error_code=type(exc).__name__,
                )
                print(f"FAILED {snapshot.snapshot_ts.isoformat()} {type(exc).__name__}: {exc}")

        print(f"Complete: succeeded={succeeded} skipped={skipped} failed={failed} mode={args.mode}")
        return 0 if failed == 0 else 2
    finally:
        store.conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
