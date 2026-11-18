"""Migrate legacy option_stream rows into a dedicated Medallion Bronze database.

Safety:
- Historical import only.
- Paper-only; no trading, live acquisition, or production cutover.
- Reads legacy source database; writes only to a dedicated Bronze database.
- Idempotent by canonical snapshot identity.
- Does not mutate or delete option_stream source rows.
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb

from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.data_platform.option_stream_history_migration import (
    OptionStreamSnapshot,
    migrate_option_stream_snapshot,
)

MIGRATION_LEDGER_SQL = """
CREATE SCHEMA IF NOT EXISTS medallion_audit;
CREATE TABLE IF NOT EXISTS medallion_audit.option_stream_migration (
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


def ensure_ledger(bronze_conn: duckdb.DuckDBPyConnection) -> None:
    bronze_conn.execute(MIGRATION_LEDGER_SQL)


def already_migrated(
    bronze_conn: duckdb.DuckDBPyConnection,
    snapshot: OptionStreamSnapshot,
) -> bool:
    row = bronze_conn.execute(
        """
        SELECT 1
        FROM medallion_audit.option_stream_migration
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
    bronze_conn: duckdb.DuckDBPyConnection,
    snapshot: OptionStreamSnapshot,
    *,
    status: str,
    result: dict[str, Any] | None = None,
    error_code: str | None = None,
) -> None:
    bronze_conn.execute(
        """
        INSERT OR REPLACE INTO medallion_audit.option_stream_migration (
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
    source_conn: duckdb.DuckDBPyConnection,
    *,
    underlying: str,
    start_date: date,
    end_date: date,
) -> list[OptionStreamSnapshot]:
    rows = source_conn.execute(
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
        if ts.tzinfo is None:
            raise ValueError("option_stream.ts must be timezone-aware")
        trading_date = ts.date()
        grouped.setdefault((underlying, trading_date, ts), []).append(record)

    return [
        OptionStreamSnapshot(
            underlying=symbol,
            trading_date=trading_date,
            snapshot_ts=ts,
            rows=tuple(records),
        )
        for (symbol, trading_date, ts), records in sorted(grouped.items())
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--bronze-db", type=Path, required=True)
    parser.add_argument("--underlying", default="NIFTY")
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    parser.add_argument("--actor-id", default="migration-operator")
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--mode", choices=["dry-run", "apply"], default="dry-run")
    args = parser.parse_args()

    if args.start_date > args.end_date:
        raise ValueError("--start-date must be <= --end-date")
    if args.source_db.resolve() == args.bronze_db.resolve():
        raise ValueError("--source-db and --bronze-db must be different files")

    source_conn = duckdb.connect(str(args.source_db), read_only=True)
    bronze_conn = duckdb.connect(str(args.bronze_db))
    try:
        BronzeEventStore(bronze_conn).initialize()
        AuditLedger(bronze_conn).initialize()
        ensure_ledger(bronze_conn)
        snapshots = load_snapshots(
            source_conn,
            underlying=args.underlying,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        print(f"Discovered {len(snapshots)} option-stream snapshots")

        succeeded = skipped = failed = 0
        for snapshot in snapshots:
            if already_migrated(bronze_conn, snapshot):
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
                    bronze_conn,
                    snapshot,
                    actor_id=args.actor_id,
                    code_revision=args.code_revision,
                )
                record_result(bronze_conn, snapshot, status="SUCCEEDED", result=result)
                succeeded += 1
                print(f"MIGRATED {snapshot.snapshot_ts.isoformat()} capture_event_id={result['capture_event_id']}")
            except Exception as exc:
                failed += 1
                record_result(
                    bronze_conn,
                    snapshot,
                    status="FAILED",
                    error_code=type(exc).__name__,
                )
                print(f"FAILED {snapshot.snapshot_ts.isoformat()} {type(exc).__name__}: {exc}")

        print(f"Complete: succeeded={succeeded} skipped={skipped} failed={failed} mode={args.mode}")
        return 0 if failed == 0 else 2
    finally:
        source_conn.close()
        bronze_conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
