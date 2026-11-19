r"""Bounded CLI for event outcome research validation archive.

Reads a reviewed JSON payload and archives persisted event outcome research
evidence to JSONL. This CLI never asserts event truth, never grants decision
eligibility, and never enables live trading.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from nse_quant.persistence.duckdb_store import DuckDBStore


class EventOutcomeResearchValidationArchiveSettings(BaseModel):
    enabled: bool = False
    max_records: int = Field(default=100, ge=1)


def _fetch_all(conn: Any, query: str, params: list[Any]) -> list[Any]:
    result = conn.execute(query, params)
    if result is not None and hasattr(result, "fetchall"):
        return result.fetchall()
    if hasattr(conn, "fetchall"):
        return conn.fetchall()
    if hasattr(conn, "query"):
        return conn.query(query, params).fetchall()
    return []


def archive_event_outcome_research(
    *,
    payload: dict[str, Any],
    settings: EventOutcomeResearchValidationArchiveSettings,
    store: DuckDBStore,
    output_path: Path,
) -> dict[str, Any]:
    if not settings.enabled:
        return {
            "status": "REJECTED",
            "reason": "event_outcome_research_validation_archive_disabled",
            "decision_eligibility_asserted": False,
        }

    required = (
        "event_id",
        "instrument",
    )
    missing = [field for field in required if payload.get(field) is None]
    if missing:
        return {
            "status": "REJECTED",
            "reason": "missing_required_fields",
            "missing": missing,
            "decision_eligibility_asserted": False,
        }

    store.conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_outcome_research_evidence (
            persistence_id VARCHAR PRIMARY KEY,
            validation_id VARCHAR,
            event_id VARCHAR,
            instrument VARCHAR,
            decision_ts TIMESTAMPTZ,
            validation JSON,
            persisted_at TIMESTAMPTZ
        )
        """
    )
    query = """
        SELECT
            persistence_id,
            validation_id,
            event_id,
            instrument,
            decision_ts,
            validation,
            persisted_at
        FROM event_outcome_research_evidence
        WHERE event_id = ?
          AND instrument = ?
        ORDER BY persisted_at DESC
        LIMIT ?
    """
    params = [
        payload["event_id"],
        payload["instrument"],
        settings.max_records,
    ]
    rows = _fetch_all(store.conn, query, params)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            record = {
                "persistence_id": row[0],
                "validation_id": row[1],
                "event_id": row[2],
                "instrument": row[3],
                "decision_ts": row[4].isoformat() if row[4] else None,
                "validation": json.loads(row[5]) if row[5] else {},
                "persisted_at": row[6].isoformat() if row[6] else None,
            }
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")

    return {
        "status": "ARCHIVED",
        "archived": len(rows),
        "output_path": str(output_path),
        "decision_eligibility_asserted": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="event-outcome-research-validation-archive",
        description="Archive bounded event outcome research evidence.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    archive = sub.add_parser("archive", help="Archive event outcome research")
    archive.add_argument("--db", required=True, help="Path to DuckDB database")
    archive.add_argument("--input", required=True, help="Path to reviewed JSON payload")
    archive.add_argument("--output", required=True, help="Path to output JSONL")
    archive.add_argument("--enabled", action="store_true", help="Enable archive")
    archive.add_argument(
        "--max-records",
        type=int,
        default=100,
        help="Maximum records",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "archive":
        parser.error("unsupported command")

    db_path = Path(args.db)
    input_path = Path(args.input)
    output_path = Path(args.output)

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

    settings = EventOutcomeResearchValidationArchiveSettings(
        enabled=args.enabled,
        max_records=args.max_records,
    )
    store = DuckDBStore(db_path)
    result = archive_event_outcome_research(
        payload=payload,
        settings=settings,
        store=store,
        output_path=output_path,
    )
    print(json.dumps(result, sort_keys=True, default=str))
    store.conn.close()
    return 0 if result.get("status") == "ARCHIVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
