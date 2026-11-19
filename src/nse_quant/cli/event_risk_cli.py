r"""Bounded CLI for event-risk evaluation.

Reads a reviewed JSON payload and evaluates event risk for an instrument using
the bounded event-risk plugin. This CLI never asserts event truth, never grants
decision eligibility, and never enables live trading.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.event_risk_plugin import (
    EventRiskPlugin,
    EventRiskSettings,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="event-risk",
        description="Evaluate event risk for an instrument.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    evaluate = sub.add_parser("evaluate", help="Evaluate event risk")
    evaluate.add_argument("--db", required=True, help="Path to DuckDB database")
    evaluate.add_argument("--input", required=True, help="Path to reviewed JSON payload")
    evaluate.add_argument("--enabled", action="store_true", help="Enable event risk")
    evaluate.add_argument(
        "--block-new-entries",
        action="store_true",
        help="Enable new-entry blackout",
    )
    evaluate.add_argument(
        "--blackout-minutes-before",
        type=int,
        default=30,
        help="Blackout minutes before event",
    )
    evaluate.add_argument(
        "--blackout-minutes-after",
        type=int,
        default=30,
        help="Blackout minutes after event",
    )
    evaluate.add_argument(
        "--allowed-event-types",
        nargs="*",
        default=["RBI_POLICY"],
        help="Allowed event types",
    )
    evaluate.add_argument(
        "--max-events",
        type=int,
        default=10,
        help="Maximum events to consider",
    )
    return parser


def run_evaluate(
    *,
    payload: dict[str, Any],
    plugin: EventRiskPlugin,
) -> dict[str, Any]:
    required = (
        "run_id",
        "instrument",
        "decision_ts",
    )
    missing = [field for field in required if payload.get(field) is None]
    if missing:
        return {
            "status": "REJECTED",
            "reason": "missing_required_fields",
            "missing": missing,
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

    result = plugin.evaluate(
        run_id=payload["run_id"],
        instrument=payload["instrument"],
        decision_ts=decision_ts,
    )
    return {
        "status": "EVALUATED" if result.get("available") else "REJECTED",
        "reason": result.get("reason"),
        "event_risk": result.get("event_risk"),
        "decision_eligibility_asserted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "evaluate":
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

    settings = EventRiskSettings(
        enabled=args.enabled,
        block_new_entries=args.block_new_entries,
        blackout_minutes_before=args.blackout_minutes_before,
        blackout_minutes_after=args.blackout_minutes_after,
        allowed_event_types=args.allowed_event_types,
        max_events=args.max_events,
    )
    store = DuckDBStore(db_path)
    plugin = EventRiskPlugin(store=store, settings=settings)
    result = run_evaluate(payload=payload, plugin=plugin)
    print(json.dumps(result, sort_keys=True))
    store.conn.close()
    return 0 if result.get("status") == "EVALUATED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
