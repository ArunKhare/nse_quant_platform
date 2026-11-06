r"""Bounded CLI for event review alerts.

Reads a reviewed JSON payload and evaluates event review alerts for open
positions using the bounded event review alert manager. This CLI never asserts
event truth, never grants decision eligibility, and never enables live trading.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from nse_quant.ops.event_review_alerts import EventReviewAlertManager
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.persistence.repositories import DecisionRepository
from nse_quant.risk.event_risk_policy import EventRiskDecision


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="event-review-alerts",
        description="Evaluate event review alerts for open positions.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    evaluate = sub.add_parser("evaluate", help="Evaluate event review alerts")
    evaluate.add_argument("--db", required=True, help="Path to DuckDB database")
    evaluate.add_argument("--input", required=True, help="Path to reviewed JSON payload")
    evaluate.add_argument("--notify", action="store_true", help="Enable notification")
    return parser


def run_evaluate(
    *,
    payload: dict[str, Any],
    manager: EventReviewAlertManager,
) -> dict[str, Any]:
    required = (
        "run_id",
        "decision",
        "open_positions",
    )
    missing = [field for field in required if payload.get(field) is None]
    if missing:
        return {
            "status": "REJECTED",
            "reason": "missing_required_fields",
            "missing": missing,
            "decision_eligibility_asserted": False,
        }

    decision_payload = payload["decision"]
    if not isinstance(decision_payload, dict):
        return {
            "status": "REJECTED",
            "reason": "decision_must_be_object",
            "decision_eligibility_asserted": False,
        }

    open_positions = payload["open_positions"]
    if not isinstance(open_positions, list):
        return {
            "status": "REJECTED",
            "reason": "open_positions_must_be_list",
            "decision_eligibility_asserted": False,
        }

    try:
        decision = EventRiskDecision(**decision_payload)
    except Exception:
        return {
            "status": "REJECTED",
            "reason": "invalid_decision",
            "decision_eligibility_asserted": False,
        }

    notify = print if payload.get("notify") else None
    result = manager.evaluate(
        run_id=payload["run_id"],
        decision=decision,
        open_positions=open_positions,
        notify=notify,
    )
    return {
        "status": "EVALUATED" if result else "NO_ALERT",
        "alert": result,
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

    store = DuckDBStore(db_path)
    decisions = DecisionRepository(store.conn)
    manager = EventReviewAlertManager(decisions=decisions)
    payload["notify"] = args.notify
    result = run_evaluate(payload=payload, manager=manager)
    print(json.dumps(result, sort_keys=True))
    store.conn.close()
    return 0 if result.get("status") in {"EVALUATED", "NO_ALERT"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
