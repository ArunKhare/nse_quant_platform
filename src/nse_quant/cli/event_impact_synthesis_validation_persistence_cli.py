r"""Bounded CLI for event impact synthesis validation persistence.

Reads a reviewed JSON payload and persists a bounded event impact validation
record. This CLI never asserts event truth, never grants decision eligibility,
and never enables live trading.
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


class EventImpactSynthesisValidationPersistenceSettings(BaseModel):
    enabled: bool = False
    max_payload_bytes: int = Field(default=65536, ge=1)


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


def persist_event_impact_validation(
    *,
    payload: dict[str, Any],
    settings: EventImpactSynthesisValidationPersistenceSettings,
    store: DuckDBStore,
) -> dict[str, Any]:
    if not settings.enabled:
        return {
            "status": "REJECTED",
            "reason": "event_impact_synthesis_validation_persistence_disabled",
            "decision_eligibility_asserted": False,
        }

    required = (
        "validation_id",
        "synthesis_id",
        "event_id",
        "instrument",
        "decision_ts",
        "validation",
    )
    missing = [field for field in required if payload.get(field) is None]
    if missing:
        return {
            "status": "REJECTED",
            "reason": "missing_required_fields",
            "missing": missing,
            "decision_eligibility_asserted": False,
        }

    payload_bytes = len(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    )
    if payload_bytes > settings.max_payload_bytes:
        return {
            "status": "REJECTED",
            "reason": "payload_too_large",
            "decision_eligibility_asserted": False,
        }

    validation = payload["validation"]
    if not isinstance(validation, dict):
        return {
            "status": "REJECTED",
            "reason": "validation_must_be_object",
            "decision_eligibility_asserted": False,
        }

    try:
        decision_ts = datetime.fromisoformat(payload["decision_ts"])
    except (TypeError, ValueError):
        return {
            "status": "REJECTED",
            "reason": "invalid_timestamp",
            "decision_eligibility_asserted": False,
        }

    persisted_at = datetime.now(UTC)
    record = {
        "persistence_id": persistence_id(
            validation_id=payload["validation_id"],
            synthesis_id=payload["synthesis_id"],
            event_id=payload["event_id"],
            instrument=payload["instrument"],
        ),
        "validation_id": payload["validation_id"],
        "synthesis_id": payload["synthesis_id"],
        "event_id": payload["event_id"],
        "instrument": payload["instrument"],
        "decision_ts": decision_ts,
        "validation": validation,
        "persisted_at": persisted_at,
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
            record["persistence_id"],
            record["validation_id"],
            record["synthesis_id"],
            record["event_id"],
            record["instrument"],
            record["decision_ts"],
            json.dumps(record["validation"], sort_keys=True, separators=(",", ":")),
            persisted_at,
        ],
    )

    return {
        "status": "PERSISTED",
        "persistence_id": record["persistence_id"],
        "decision_eligibility_asserted": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="event-impact-synthesis-validation-persistence",
        description="Persist bounded event impact synthesis validation.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    persist = sub.add_parser("persist", help="Persist event impact validation")
    persist.add_argument("--db", required=True, help="Path to DuckDB database")
    persist.add_argument("--input", required=True, help="Path to reviewed JSON payload")
    persist.add_argument("--enabled", action="store_true", help="Enable persistence")
    persist.add_argument(
        "--max-payload-bytes",
        type=int,
        default=65536,
        help="Maximum payload size",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "persist":
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

    settings = EventImpactSynthesisValidationPersistenceSettings(
        enabled=args.enabled,
        max_payload_bytes=args.max_payload_bytes,
    )
    store = DuckDBStore(db_path)
    result = persist_event_impact_validation(
        payload=payload,
        settings=settings,
        store=store,
    )
    print(json.dumps(result, sort_keys=True, default=str))
    store.conn.close()
    return 0 if result.get("status") == "PERSISTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
