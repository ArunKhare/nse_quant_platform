"""Importer status
The importer should now be treated as a dormant utility, not an active data pipeline. Your"""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import duckdb


def _is_sqlite(path: Path) -> bool:
    with path.open("rb") as handle:
        return handle.read(16) == b"SQLite format 3\x00"


class LegacyOptionsImporter:
    """Maps legacy option-stream rows into the canonical DuckDB option_stream table."""

    REQUIRED_COLUMNS: ClassVar[set[str]] = {
        "snapshot_ist",
        "expiry",
        "strike",
        "kind",
        "symbol",
        "token",
        "lot_size",
        "spot",
    }
    COLUMN_ALIASES: ClassVar[dict[str, str]] = {
        "snapshot_ist": "timestamp",
        "token": "instrument_token",
        "kind": "option_type",
        "symbol": "tradingsymbol",
        "option_price": "ltp",
    }

    def __init__(self, duckdb_conn: Any, legacy_db_path: str | Path) -> None:
        self.conn = duckdb_conn
        self.legacy_db_path = Path(legacy_db_path)

        if not self.legacy_db_path.exists():
            raise FileNotFoundError(f"Legacy database not found: {self.legacy_db_path}")

    def inspect(self) -> dict[str, Any]:
        connection, _ = self._open_legacy_connection()

        try:
            if self._is_sqlite_source():
                cursor = connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                    """
                )
            else:
                cursor = connection.execute("SHOW TABLES")

            tables = [row[0] for row in cursor.fetchall()]
        finally:
            connection.close()

        return {"tables": tables}

    def import_table(
        self,
        table_name: str,
        batch_size: int = 5_000,
        dry_run: bool = True,
    ) -> dict[str, int]:
        connection, cursor = self._open_legacy_connection(table_name)

        try:
            source_columns = {description[0].lower() for description in cursor.description}

            mapped_columns = {self.COLUMN_ALIASES.get(column, column) for column in source_columns}

            missing = self.REQUIRED_COLUMNS - mapped_columns

            if missing:
                raise ValueError(f"Legacy table missing required columns: {sorted(missing)}")

            inserted = 0
            skipped = 0

            while True:
                rows = cursor.fetchmany(batch_size)

                if not rows:
                    break

                prepared: list[tuple[Any, ...]] = []

                for row in rows:
                    record = {key.lower(): value for key, value in dict(row).items()}

                    normalized = self._normalize(record)

                    if normalized is None:
                        skipped += 1
                        continue

                    prepared.append(normalized)

                if prepared and not dry_run:
                    placeholders = ",".join(["?"] * 22)

                    self.conn.executemany(
                        f"""
                        INSERT OR REPLACE INTO option_stream
                        VALUES ({placeholders})
                        """,
                        prepared,
                    )

                inserted += len(prepared)

            return {
                "inserted": inserted,
                "skipped": skipped,
                "dry_run": int(dry_run),
            }

        finally:
            connection.close()

    def _normalize(self, record: dict[str, Any]) -> tuple[Any, ...] | None:
        try:
            record = {self.COLUMN_ALIASES.get(key, key): value for key, value in record.items()}

            ts = self._parse_datetime(record["timestamp"])
            expiry = self._parse_date(record["expiry"])
            option_type = str(record["option_type"]).upper()

            if option_type not in {"CE", "PE"}:
                return None

            tradingsymbol = str(record["tradingsymbol"])
            underlying = self._derive_underlying(tradingsymbol)

            if underlying != "NIFTY":
                return None

            return (
                f"legacy:{record.get('run_id', 'import')}",
                ts,
                underlying,
                expiry,
                float(record["strike"]),
                option_type,
                tradingsymbol,
                int(record["instrument_token"]),
                int(record["lot_size"]),
                float(record["spot"]),
                self._optional_float(record.get("ltp")),
                self._optional_float(record.get("bid")),
                self._optional_float(record.get("ask")),
                self._optional_int(record.get("volume")),
                self._optional_int(record.get("oi")),
                self._optional_float(record.get("iv")),
                self._optional_float(record.get("delta")),
                self._optional_float(record.get("gamma")),
                self._optional_float(record.get("vega")),
                self._optional_float(record.get("theta")),
                "legacy_import",
                "{}",
            )

        except (TypeError, ValueError, KeyError):
            return None

    def validate_import(
        self,
        underlying: str,
        minimum_observations: int = 30,
    ) -> dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT
                COUNT(*) AS observation_count,
                MIN(ts) AS first_observation,
                MAX(ts) AS last_observation,
                AVG(iv) AS average_iv,
                MIN(iv) AS minimum_iv,
                MAX(iv) AS maximum_iv
            FROM (
                SELECT
                    ts,
                    AVG(iv) AS iv
                FROM option_stream
                WHERE underlying = ?
                AND iv IS NOT NULL
                GROUP BY ts
            )
            """,
            [underlying],
        ).fetchone()

        observation_count = int(row[0] or 0)

        return {
            "underlying": underlying,
            "observation_count": observation_count,
            "minimum_observations": minimum_observations,
            "ready_for_iv_rank": (observation_count >= minimum_observations),
            "first_observation": row[1],
            "last_observation": row[2],
            "average_iv": float(row[3]) if row[3] is not None else None,
            "minimum_iv": float(row[4]) if row[4] is not None else None,
            "maximum_iv": float(row[5]) if row[5] is not None else None,
        }

    def _is_sqlite_source(self) -> bool:
        return _is_sqlite(self.legacy_db_path)

    def _open_legacy_connection(
        self,
        table_name: str | None = None,
    ) -> tuple[Any, Any]:
        if self._is_sqlite_source():
            connection = sqlite3.connect(self.legacy_db_path)
            connection.row_factory = sqlite3.Row

            cursor = (
                connection.execute(f'SELECT * FROM "{table_name}"')
                if table_name
                else connection.execute("SELECT 1")
            )

            return connection, cursor

        duck_connection = duckdb.connect(
            str(self.legacy_db_path),
            read_only=True,
        )

        duck_cursor = (
            duck_connection.execute(f'SELECT * FROM "{table_name}"')
            if table_name
            else duck_connection.execute("SELECT 1")
        )

        return duck_connection, duck_cursor

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)

        parsed = datetime.fromisoformat(str(value))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    @staticmethod
    def _parse_date(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.date()

        return datetime.fromisoformat(str(value)).date()

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        return None if value in (None, "") else float(value)

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        return None if value in (None, "") else int(value)

    @staticmethod
    def _derive_underlying(tradingsymbol: str) -> str:
        match = re.match(r"^([A-Z&\-]+?)(?:\d{2}[A-Z]{3}\d*)", tradingsymbol)

        if not match:
            return ""

        return match.group(1)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Import legacy options market data")
    parser.add_argument(
        "--legacy-db",
        required=True,
        help="Path to legacy SQLite database",
    )
    parser.add_argument(
        "--table",
        default="option_stream",
        help="Legacy table name",
    )
    parser.add_argument(
        "--underlying",
        default="NIFTY",
        help="Underlying used for validation",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate mapping without writing",
    )
    args = parser.parse_args()

    from nse_quant.persistence.duckdb_store import DuckDBStore

    store = DuckDBStore()
    importer = LegacyOptionsImporter(
        store.conn,
        args.legacy_db,
    )

    result = importer.import_table(
        args.table,
        dry_run=args.dry_run,
    )
    validation = importer.validate_import(
        args.underlying,
        minimum_observations=30,
    )

    print(result)
    print(validation)

    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
