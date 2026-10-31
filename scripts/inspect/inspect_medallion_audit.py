"""Read the medallion audit ledger without creating a database or schema."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--job-id", default=None)
    args = parser.parse_args(argv)
    if not args.db.is_file():
        parser.error("Audit database must already exist")
    conn = duckdb.connect(str(args.db), read_only=True)
    try:
        query = """
            SELECT j.job_id, j.parent_job_id, j.command_name, e.event_index,
                   e.state, e.recorded_at, e.reason_code
            FROM medallion_audit.jobs j
            JOIN medallion_audit.job_events e ON j.job_id = e.job_id
        """
        parameters = []
        if args.job_id is not None:
            query += " WHERE j.job_id = ?"
            parameters.append(args.job_id)
        query += " ORDER BY j.created_at, j.job_id, e.event_index"
        for row in conn.execute(query, parameters).fetchall():
            print(row)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
