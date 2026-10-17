"""Importer for the legacy options_market_data.db SQLite database."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar


class LegacyOptionsImporter:
    """Maps legacy option-stream rows into the canonical DuckDB option_stream table."""

    REQUIRED_COLUMNS: ClassVar[set[str]] = {
        "timestamp",
        "underlying",
        "expiry",
        "strike",
        "option_type",
        "tradingsymbol",
        "instrument_token",
        "lot_size",
        "spot",
    }

    def __init__(self, duckdb_conn: Any, legacy_db_path: str | Path) -> None:
        self.conn = duckdb_conn
        self.legacy_db_path = Path(legacy_db_path)

        if not self.legacy_db_path.exists():
            raise FileNotFoundError(f"Legacy database not found: {self.legacy_db_path}")

    def inspect(self) -> dict[str, Any]:
        with sqlite3.connect(self.legacy_db_path) as connection:
            cursor = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            )
            tables = [row[0] for row in cursor.fetchall()]

        return {"tables": tables}

    def import_table(
        self,
        table_name: str,
        batch_size: int = 5_000,
        dry_run: bool = True,
    ) -> dict[str, int]:
        with sqlite3.connect(self.legacy_db_path) as connection:
            connection.row_factory = sqlite3.Row
            cursor = connection.execute(f"SELECT * FROM {table_name}")
            columns = {description[0].lower() for description in cursor.description}

            missing = self.REQUIRED_COLUMNS - columns
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
                        f"INSERT OR REPLACE INTO option_stream VALUES ({placeholders})",
                        prepared,
                    )

                inserted += len(prepared)

        return {"inserted": inserted, "skipped": skipped, "dry_run": int(dry_run)}

    def _normalize(self, record: dict[str, Any]) -> tuple[Any, ...] | None:
        try:
            ts = self._parse_datetime(record["timestamp"])
            expiry = self._parse_date(record["expiry"])
            option_type = str(record["option_type"]).upper()

            if option_type not in {"CE", "PE"}:
                return None

            return (
                f"legacy:{record.get('run_id', 'import')}",
                ts,
                str(record["underlying"]).upper(),
                expiry,
                float(record["strike"]),
                option_type,
                str(record["tradingsymbol"]),
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