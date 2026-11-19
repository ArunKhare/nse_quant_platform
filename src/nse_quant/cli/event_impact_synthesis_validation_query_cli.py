r"""Bounded CLI for event impact synthesis validation query.

Reads a reviewed JSON payload and queries persisted event impact validation
evidence. This CLI never asserts event truth, never grants decision
eligibility, and never enables live trading.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from nse_quant.persistence.duckdb_store import DuckDBStore


class EventImpactSynthesisValidationQuerySettings(BaseModel):
    enabled: bool = False
    max_records: int = Field(default=100, ge=1)


def query_event_impact_validation(
    *,
    payload: dict[str, Any],
    settings: EventImpactSynthesisValidationQuerySettings,
    store: DuckDBStore,
) -> dict[str, Any]:
    if not settings.enabled:
        return {
            "status": "REJECTED",
            "reason": "event_impact_synthesis_validation_query_disabled",
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
    rows = store.conn.execute(
        """
        SELECT
            persistence_id,
            validation_id,
            synthesis_id,
            event_id,
            instrument,
            decision_ts,
            validation,
            persisted_at
        FROM event_impact_synthesis_validation_evidence
        WHERE event_id = ?
          AND instrument = ?
        ORDER BY persisted_at DESC
        LIMIT ?
        """,
        [
            payload["event_id"],
            payload["instrument"],
            settings.max_records,
        ],
    ).fetchall()

    records = []
    for row in rows:
        records.append(
            {
                "persistence_id": row[0],
                "validation_id": row[1],
                "synthesis_id": row[2],
                "event_id": row[3],
                "instrument": row[4],
                "decision_ts": row[5].isoformat() if row[5] else None,
                "validation": json.loads(row[6]) if row[6] else None,
                "persisted_at": row[7].isoformat() if row[7] else None,
            }
        )

    return {
        "status": "QUERIED",
        "records": records,
        "count": len(records),
        "decision_eligibility_asserted": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="event-impact-synthesis-validation-query",
        description="Query bounded event impact validation evidence.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    query = sub.add_parser("query", help="Query event impact validation evidence")
    query.add_argument("--db", required=True, help="Path to DuckDB database")
    query.add_argument("--input", required=True, help="Path to reviewed JSON payload")
    query.add_argument("--enabled", action="store_true", help="Enable query")
    query.add_argument(
        "--max-records",
        type=int,
        default=100,
        help="Maximum records",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "query":
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

    settings = EventImpactSynthesisValidationQuerySettings(
        enabled=args.enabled,
        max_records=args.max_records,
    )
    store = DuckDBStore(db_path)
    result = query_event_impact_validation(
        payload=payload,
        settings=settings,
        store=store,
    )
    print(json.dumps(result, sort_keys=True, default=str))
    store.conn.close()
    return 0 if result.get("status") == "QUERIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
