r"""Bounded CLI for event outcome research validation vacuum.

Reads a reviewed JSON payload and vacuums persisted event outcome research
evidence from DuckDB. This CLI never asserts event truth, never grants decision
eligibility, and never enables live trading.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from nse_quant.persistence.duckdb_store import DuckDBStore


class EventOutcomeResearchValidationVacuumSettings(BaseModel):
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


def vacuum_event_outcome_research(
    *,
    payload: dict[str, Any],
    settings: EventOutcomeResearchValidationVacuumSettings,
    store: DuckDBStore,
) -> dict[str, Any]:
    if not settings.enabled:
        return {
            "status": "REJECTED",
            "reason": "event_outcome_research_validation_vacuum_disabled",
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

    vacuumed = 0
    for row in rows:
        store.conn.execute(
            """
            DELETE FROM event_outcome_research_evidence
            WHERE persistence_id = ?
            """,
            [row[0]],
        )
        vacuumed += 1

    return {
        "status": "VACUUMED",
        "vacuumed": vacuumed,
        "decision_eligibility_asserted": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="event-outcome-research-validation-vacuum",
        description="Vacuum bounded event outcome research evidence.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    vacuum = sub.add_parser("vacuum", help="Vacuum event outcome research")
    vacuum.add_argument("--db", required=True, help="Path to DuckDB database")
    vacuum.add_argument("--input", required=True, help="Path to reviewed JSON payload")
    vacuum.add_argument("--enabled", action="store_true", help="Enable vacuum")
    vacuum.add_argument(
        "--max-records",
        type=int,
        default=100,
        help="Maximum records",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "vacuum":
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

    settings = EventOutcomeResearchValidationVacuumSettings(
        enabled=args.enabled,
        max_records=args.max_records,
    )
    store = DuckDBStore(db_path)
    result = vacuum_event_outcome_research(
        payload=payload,
        settings=settings,
        store=store,
    )
    print(json.dumps(result, sort_keys=True, default=str))
    store.conn.close()
    return 0 if result.get("status") == "VACUUMED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
