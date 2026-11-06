r"""Bounded CLI for event reaction capture.

Reads a reviewed JSON payload and captures a bounded post-event market reaction
using the event reaction recorder. This CLI never asserts event truth, never
grants decision eligibility, and never enables live trading.
"""

from __future__ import annotations

import argparse
import importlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from nse_quant.persistence.duckdb_store import DuckDBStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="event-reaction-capture",
        description="Capture bounded post-event market reaction.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    capture = sub.add_parser("capture", help="Capture event reaction")
    capture.add_argument("--db", required=True, help="Path to DuckDB database")
    capture.add_argument("--input", required=True, help="Path to reviewed JSON payload")
    return parser


def run_capture(
    *,
    payload: dict[str, Any],
    recorder: Any,
) -> dict[str, Any]:
    required = (
        "event",
        "instrument",
        "observation_window_minutes",
        "baseline",
        "observed",
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
        result = recorder.capture(
            event=payload["event"],
            instrument=payload["instrument"],
            observation_window_minutes=payload["observation_window_minutes"],
            baseline=payload["baseline"],
            observed=payload["observed"],
        )
    except TypeError:
        return {
            "status": "REJECTED",
            "reason": "recorder_signature_mismatch",
            "decision_eligibility_asserted": False,
        }

    return {
        "status": "CAPTURED" if result else "REJECTED",
        "reaction": result,
        "decision_eligibility_asserted": False,
    }


def _load_recorder_class():
    try:
        module = importlib.import_module("nse_quant.research.event_reactions")
    except ImportError:
        module = importlib.import_module("nse_quant.research.event_reaction_capture")
    return module.EventReactionRecorder


def main(
    argv: list[str] | None = None,
    *,
    recorder_factory: Callable[[Any], Any] | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "capture":
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
    if recorder_factory is None:
        recorder_class = _load_recorder_class()
        try:
            recorder = recorder_class(store=store)
        except TypeError:
            recorder = recorder_class(store)
    else:
        recorder = recorder_factory(store)

    result = run_capture(payload=payload, recorder=recorder)
    print(json.dumps(result, sort_keys=True, default=str))
    store.conn.close()
    return 0 if result.get("status") == "CAPTURED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
