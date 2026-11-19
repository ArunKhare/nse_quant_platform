r"""Bounded CLI for event impact mapping.

Reads a reviewed JSON payload and maps a reviewed market event to instrument
impact evidence using the event impact mapper. This CLI never asserts event
truth, never grants decision eligibility, and never enables live trading.
"""

from __future__ import annotations

import argparse
import importlib
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from nse_quant.persistence.duckdb_store import DuckDBStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="event-impact-mapping",
        description="Map reviewed market event to instrument impact evidence.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    map_cmd = sub.add_parser("map", help="Map event to instrument impact")
    map_cmd.add_argument("--db", required=True, help="Path to DuckDB database")
    map_cmd.add_argument("--input", required=True, help="Path to reviewed JSON payload")
    map_cmd.add_argument("--enabled", action="store_true", help="Enable mapping")
    map_cmd.add_argument(
        "--blackout-minutes-before",
        type=int,
        default=30,
        help="Blackout minutes before event",
    )
    map_cmd.add_argument(
        "--blackout-minutes-after",
        type=int,
        default=30,
        help="Blackout minutes after event",
    )
    return parser


def run_map(
    *,
    payload: dict[str, Any],
    mapper: Any,
) -> dict[str, Any]:
    required = (
        "event_id",
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

    try:
        result = mapper.map(
            event_id=payload["event_id"],
            instrument=payload["instrument"],
            decision_ts=decision_ts,
        )
    except TypeError:
        return {
            "status": "REJECTED",
            "reason": "mapper_signature_mismatch",
            "decision_eligibility_asserted": False,
        }

    return {
        "status": "MAPPED" if result else "REJECTED",
        "mapping": result,
        "decision_eligibility_asserted": False,
    }


def _load_mapper_class():
    try:
        module = importlib.import_module("nse_quant.research.event_impact_mapping")
    except ImportError:
        module = importlib.import_module("nse_quant.research.event_impact")
    return module.EventImpactMapper


def main(
    argv: list[str] | None = None,
    *,
    mapper_factory: Callable[[Any], Any] | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "map":
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
    if mapper_factory is None:
        mapper_class = _load_mapper_class()
        try:
            settings = type(
                "Settings",
                (),
                {
                    "enabled": args.enabled,
                    "blackout_minutes_before": args.blackout_minutes_before,
                    "blackout_minutes_after": args.blackout_minutes_after,
                },
            )()
            mapper = mapper_class(store=store, settings=settings)
        except TypeError:
            try:
                mapper = mapper_class(store=store)
            except TypeError:
                mapper = mapper_class(store)
    else:
        mapper = mapper_factory(store)

    result = run_map(payload=payload, mapper=mapper)
    print(json.dumps(result, sort_keys=True, default=str))
    store.conn.close()
    return 0 if result.get("status") == "MAPPED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
