r"""Bounded CLI for event impact synthesis validation import.

Reads a reviewed JSON export file and imports bounded event impact validation
records into DuckDB. This CLI never asserts event truth, never grants decision
eligibility, and never enables live trading.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from nse_quant.persistence.duckdb_store import DuckDBStore


class EventImpactSynthesisValidationImportSettings(BaseModel):
    enabled: bool = False
    max_records: int = Field(default=100, ge=1)
    max_input_bytes: int = Field(default=1048576, ge=1)


def persistence_id(
    *,
    validation_id: str,
    synthesis_id: str,
    event_id: str,
    instrument: str,
) -> str:
    canonical = json.dumps(
        {
            "validation_id": validation_id,
            "synthesis_id": synthesis_id,
            "event_id": event_id,
            "instrument": instrument,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def import_event_impact_validation(
    *,
    payload: dict[str, Any],
    settings: EventImpactSynthesisValidationImportSettings,
    store: DuckDBStore,
) -> dict[str, Any]:
    if not settings.enabled:
        return {
            "status": "REJECTED",
            "reason": "event_impact_synthesis_validation_import_disabled",
            "decision_eligibility_asserted": False,
        }

    required = (
        "event_id",
        "instrument",
        "records",
    )
    missing = [field for field in required if payload.get(field) is None]
    if missing:
        return {
            "status": "REJECTED",
            "reason": "missing_required_fields",
            "missing": missing,
            "decision_eligibility_asserted": False,
        }

    records = payload["records"]
    if not isinstance(records, list):
        return {
            "status": "REJECTED",
            "reason": "records_must_be_list",
            "decision_eligibility_asserted": False,
        }

    if len(records) > settings.max_records:
        return {
            "status": "REJECTED",
            "reason": "too_many_records",
            "decision_eligibility_asserted": False,
        }

    input_bytes = len(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    )
    if input_bytes > settings.max_input_bytes:
        return {
            "status": "REJECTED",
            "reason": "input_too_large",
            "decision_eligibility_asserted": False,
        }

    store.conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_impact_synthesis_validation_evidence (
            persistence_id VARCHAR PRIMARY KEY,
            validation_id VARCHAR,
            synthesis_id VARCHAR,
            event_id VARCHAR,
            instrument VARCHAR,
            decision_ts TIMESTAMPTZ,
            validation JSON,
            persisted_at TIMESTAMPTZ
        )
        """
    )

    imported = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        required_record = (
            "validation_id",
            "synthesis_id",
            "event_id",
            "instrument",
            "decision_ts",
            "validation",
        )
        if any(record.get(field) is None for field in required_record):
            continue
        try:
            decision_ts = datetime.fromisoformat(record["decision_ts"])
        except (TypeError, ValueError):
            continue
        validation = record["validation"]
        if not isinstance(validation, dict):
            continue
        persisted_at = datetime.now(UTC)
        persistence = persistence_id(
            validation_id=record["validation_id"],
            synthesis_id=record["synthesis_id"],
            event_id=record["event_id"],
            instrument=record["instrument"],
        )
        store.conn.execute(
            """
            INSERT OR REPLACE INTO event_impact_synthesis_validation_evidence (
                persistence_id,
                validation_id,
                synthesis_id,
                event_id,
                instrument,
                decision_ts,
                validation,
                persisted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                persistence,
                record["validation_id"],
                record["synthesis_id"],
                record["event_id"],
                record["instrument"],
                decision_ts,
                json.dumps(validation, sort_keys=True, separators=(",", ":")),
                persisted_at,
            ],
        )
        imported += 1

    return {
        "status": "IMPORTED",
        "imported": imported,
        "decision_eligibility_asserted": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="event-impact-synthesis-validation-import",
        description="Import bounded event impact validation records.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    import_cmd = sub.add_parser("import", help="Import event impact validation records")
    import_cmd.add_argument("--db", required=True, help="Path to DuckDB database")
    import_cmd.add_argument("--input", required=True, help="Path to reviewed JSON export")
    import_cmd.add_argument("--enabled", action="store_true", help="Enable import")
    import_cmd.add_argument(
        "--max-records",
        type=int,
        default=100,
        help="Maximum records",
    )
    import_cmd.add_argument(
        "--max-input-bytes",
        type=int,
        default=1048576,
        help="Maximum input size",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "import":
        parser.error("unsupported command")

    db_path = Path(args.db)
    input_path = Path(args.input)

    if not db_path.exists():
        print(
            json.dumps(
                {
                    "status": "REJECTED",
                    "reason": "database_not_found",
                    "decision_eligibility_asserted": False,
                }
            )
        )
        return 2

    if not input_path.exists():
        print(
            json.dumps(
                {
                    "status": "REJECTED",
                    "reason": "input_file_not_found",
                    "decision_eligibility_asserted": False,
                }
            )
        )
        return 2

    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        print(
            json.dumps(
                {
                    "status": "REJECTED",
                    "reason": "invalid_input_file",
                    "decision_eligibility_asserted": False,
                }
            )
        )
        return 2

    if not isinstance(payload, dict):
        print(
            json.dumps(
                {
                    "status": "REJECTED",
                    "reason": "input_must_be_object",
                    "decision_eligibility_asserted": False,
                }
            )
        )
        return 2

    settings = EventImpactSynthesisValidationImportSettings(
        enabled=args.enabled,
        max_records=args.max_records,
        max_input_bytes=args.max_input_bytes,
    )
    store = DuckDBStore(db_path)
    result = import_event_impact_validation(
        payload=payload,
        settings=settings,
        store=store,
    )
    print(json.dumps(result, sort_keys=True, default=str))
    store.conn.close()
    return 0 if result.get("status") == "IMPORTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
