"""Read-only Silver option-stream schema and sample inspector.

Prints exact Silver column names/types and a small non-sensitive sample so the
Gold feature contract can be implemented against the actual schema. No writes,
no migration, no feature computation, no live acquisition, no trading.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--silver-db", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args(argv)

    conn = duckdb.connect(str(args.silver_db), read_only=True)
    try:
        catalog_row = conn.execute("SELECT current_catalog()").fetchone()
        assert catalog_row is not None
        catalog = str(catalog_row[0])

        tables = [
            "silver.option_stream_revisions",
            "silver.option_stream_observations",
        ]
        output = {}
        for table in tables:
            schema_name, table_name = table.split(".", 1)
            qualified_table = f'"{catalog}"."{schema_name}"."{table_name}"'

            columns = conn.execute(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_catalog = ?
                  AND table_schema = ?
                  AND table_name = ?
                ORDER BY ordinal_position
                """,
                [catalog, schema_name, table_name],
            ).fetchall()
            if not columns:
                raise SystemExit(f"MISSING_SILVER_TABLE: {table}")

            count_row = conn.execute(f"SELECT COUNT(*) FROM {qualified_table}").fetchone()
            assert count_row is not None
            row_count = int(count_row[0])

            output[table] = {
                "columns": [{"name": name, "type": kind, "nullable": nullable} for name, kind, nullable in columns],
                "row_count": row_count,
                "sample": [
                    dict(zip([name for name, _kind, _nullable in columns], row, strict=True))
                    for row in conn.execute(f"SELECT * FROM {qualified_table} LIMIT ?", [args.limit]).fetchall()
                ],
            }
        print(json.dumps(output, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
