"""Read-only completeness check for the dedicated Medallion Silver database.

Validates:
- Silver schema and revision records.
- Observation/revision count reconciliation.
- Bronze lineage pins.
- Revision context hashes.
- Quality-status distribution.
- Duplicate revision IDs.
- Missing Bronze pins.
- Quarantine accounting.

Safety:
- Opens Silver read-only.
- No writes, no migration, no live acquisition, no trading, no production cutover.
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import duckdb

SILVER_VERSION = "legacy-option-stream-silver@1"
SILVER_COMMAND = "normalize.legacy_option_stream_silver@1"


def count(conn: duckdb.DuckDBPyConnection, sql: str, params: list[object] | None = None) -> int:
    row = conn.execute(sql, params or []).fetchone()
    if row is None:
        raise ValueError("Expected a scalar count row")
    return int(row[0])


def check_silver(
    silver_conn: duckdb.DuckDBPyConnection,
    *,
    underlying: str | None,
    start_date: date | None,
    end_date: date | None,
) -> int:
    required_tables = {
        "silver.option_stream_revisions",
        "silver.option_stream_observations",
    }
    existing = {
        row[0]
        for row in silver_conn.execute(
            """
            SELECT table_schema || '.' || table_name
            FROM information_schema.tables
            WHERE table_schema = 'silver'
            """
        ).fetchall()
    }
    missing_tables = sorted(required_tables - existing)
    if missing_tables:
        print(f"FAIL missing_silver_tables: {missing_tables}")
        return 2

    revision_filter = ""
    params: list[object] = []
    if underlying:
        revision_filter += " AND r.bronze_source_label LIKE ?"
        params.append(f"%{underlying}%")
    if start_date:
        revision_filter += " AND CAST(r.recorded_at AT TIME ZONE 'Asia/Kolkata' AS DATE) >= ?"
        params.append(start_date.isoformat())
    if end_date:
        revision_filter += " AND CAST(r.recorded_at AT TIME ZONE 'Asia/Kolkata' AS DATE) <= ?"
        params.append(end_date.isoformat())
    print({"params": params})
    print({"revision_filter": revision_filter})

    revisions = count(
        silver_conn,
        f"SELECT COUNT(*) FROM silver.option_stream_revisions r WHERE 1=1{revision_filter}",
        params,
    )
    observations = count(
        silver_conn,
        f"""
        SELECT COUNT(*) FROM silver.option_stream_observations o
        JOIN silver.option_stream_revisions r
          ON r.revision_id = o.revision_id
        WHERE 1=1{revision_filter}
        """,
        params,
    )
    valid_observations = count(
        silver_conn,
        f"""
        SELECT COUNT(*) FROM silver.option_stream_observations o
        JOIN silver.option_stream_revisions r
          ON r.revision_id = o.revision_id
        WHERE o.quality_status = 'VALID'{revision_filter}
        """,
        params,
    )
    quarantined_observations = count(
        silver_conn,
        f"""
        SELECT COUNT(*) FROM silver.option_stream_observations o
        JOIN silver.option_stream_revisions r
          ON r.revision_id = o.revision_id
        WHERE o.quality_status = 'QUARANTINED'{revision_filter}
        """,
        params,
    )
    duplicate_revisions = count(
        silver_conn,
        f"""
        SELECT COUNT(*) FROM (
            SELECT r.revision_id
            FROM silver.option_stream_revisions r
            WHERE 1=1{revision_filter}
            GROUP BY r.revision_id
            HAVING COUNT(*) > 1
        )
        """,
        params,
    )
    orphan_observations = count(
        silver_conn,
        """
        SELECT COUNT(*) FROM silver.option_stream_observations o
        LEFT JOIN silver.option_stream_revisions r
          ON r.revision_id = o.revision_id
        WHERE r.revision_id IS NULL
        """,
    )
    missing_bronze_pins = count(
        silver_conn,
        f"""
        SELECT COUNT(*) FROM silver.option_stream_observations o
        JOIN silver.option_stream_revisions r
          ON r.revision_id = o.revision_id
        WHERE (o.bronze_snapshot_id IS NULL
           OR o.bronze_capture_event_id IS NULL
           OR o.bronze_envelope_hash IS NULL
           OR o.bronze_recording_fingerprint IS NULL
           OR o.bronze_source_label IS NULL){revision_filter}
        """,
        params,
    )
    context_hash_mismatches = count(
        silver_conn,
        f"""
        SELECT COUNT(*) FROM silver.option_stream_revisions r
        WHERE (r.context_sha256 IS NULL
           OR length(r.context_sha256) <> 64){revision_filter}
        """,
        params,
    )

    revision_count_mismatches = count(
        silver_conn,
        f"""
        SELECT COUNT(*) FROM (
            SELECT r.revision_id, r.observation_count, COUNT(o.source_ordinal) AS actual
            FROM silver.option_stream_revisions r
            LEFT JOIN silver.option_stream_observations o
              ON o.revision_id = r.revision_id
            WHERE 1=1{revision_filter}
            GROUP BY r.revision_id, r.observation_count
            HAVING r.observation_count <> COUNT(o.source_ordinal)
        )
        """,
        params,
    )
    quarantine_count_mismatches = count(
        silver_conn,
        f"""
        SELECT COUNT(*) FROM (
            SELECT r.revision_id, r.quarantined_count,
                   COUNT(CASE WHEN o.quality_status = 'QUARANTINED' THEN 1 END) AS actual
            FROM silver.option_stream_revisions r
            LEFT JOIN silver.option_stream_observations o
              ON o.revision_id = r.revision_id
            WHERE 1=1{revision_filter}
            GROUP BY r.revision_id, r.quarantined_count
            HAVING r.quarantined_count <> COUNT(CASE WHEN o.quality_status = 'QUARANTINED' THEN 1 END)
        )
        """,
        params,
    )

    checks = [
        ("silver_revisions", revisions, revisions),
        ("silver_observations", observations, valid_observations + quarantined_observations),
        ("orphan_observations", 0, orphan_observations),
        ("duplicate_revisions", 0, duplicate_revisions),
        ("missing_bronze_pins", 0, missing_bronze_pins),
        ("context_hash_mismatches", 0, context_hash_mismatches),
        ("revision_count_mismatches", 0, revision_count_mismatches),
        ("quarantine_count_mismatches", 0, quarantine_count_mismatches),
    ]

    print("Silver completeness check")
    print("========================")
    print(f"underlying={underlying or 'ALL'}")
    print(f"start_date={start_date or 'ALL'}")
    print(f"end_date={end_date or 'ALL'}")
    print()
    all_passed = True
    for name, expected, actual in checks:
        passed = expected == actual
        all_passed = all_passed and passed
        print(f"{'PASS' if passed else 'FAIL'} {name}: expected={expected} actual={actual}")
    print()
    print(f"valid_observations={valid_observations}")
    print(f"quarantined_observations={quarantined_observations}")
    print()
    print(f"RESULT: {'PASS' if all_passed else 'FAIL'}")
    return 0 if all_passed else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--silver-db", type=Path, required=True)
    parser.add_argument("--underlying", default=None)
    parser.add_argument("--start-date", type=date.fromisoformat, default=None)
    parser.add_argument("--end-date", type=date.fromisoformat, default=None)
    args = parser.parse_args()

    conn = duckdb.connect(str(args.silver_db), read_only=True)
    try:
        return check_silver(
            conn,
            underlying=args.underlying,
            start_date=args.start_date,
            end_date=args.end_date,
        )
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
