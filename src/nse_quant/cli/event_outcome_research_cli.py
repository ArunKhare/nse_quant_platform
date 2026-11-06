r"""Bounded CLI for event outcome research.

Reads a reviewed JSON payload and builds a bounded event outcome research panel
for an instrument. This CLI never asserts event truth, never grants decision
eligibility, and never enables live trading.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class EventOutcomeResearchSettings(BaseModel):
    enabled: bool = False
    observation_window_minutes: int = Field(default=60, ge=1)
    max_payload_bytes: int = Field(default=65536, ge=1)


def panel_id(
    *,
    event_id: str,
    instrument: str,
    observation_window_minutes: int,
) -> str:
    canonical = json.dumps(
        {
            "event_id": event_id,
            "instrument": instrument,
            "observation_window_minutes": observation_window_minutes,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def build_event_outcome_panel(
    *,
    payload: dict[str, Any],
    settings: EventOutcomeResearchSettings,
) -> dict[str, Any]:
    if not settings.enabled:
        return {
            "status": "REJECTED",
            "reason": "event_outcome_research_disabled",
            "decision_eligibility_asserted": False,
        }

    required = (
        "event_id",
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
        window = int(payload["observation_window_minutes"])
    except (TypeError, ValueError):
        return {
            "status": "REJECTED",
            "reason": "invalid_window",
            "decision_eligibility_asserted": False,
        }

    if window <= 0 or window > settings.observation_window_minutes:
        return {
            "status": "REJECTED",
            "reason": "window_out_of_bounds",
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

    baseline = payload["baseline"]
    observed = payload["observed"]
    if not isinstance(baseline, dict) or not isinstance(observed, dict):
        return {
            "status": "REJECTED",
            "reason": "baseline_and_observed_must_be_objects",
            "decision_eligibility_asserted": False,
        }

    def delta(field: str) -> float | None:
        before = baseline.get(field)
        after = observed.get(field)
        if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
            return None
        return float(after) - float(before)

    spot_return = None
    before_spot = baseline.get("spot")
    after_spot = observed.get("spot")
    if (
        isinstance(before_spot, (int, float))
        and isinstance(after_spot, (int, float))
        and float(before_spot) != 0.0
    ):
        spot_return = (float(after_spot) - float(before_spot)) / float(before_spot) * 100.0

    panel = {
        "plugin": "event_outcome_research",
        "available": True,
        "event_id": payload["event_id"],
        "instrument": payload["instrument"],
        "observation_window_minutes": window,
        "spot_return_pct": spot_return,
        "realized_range_points": delta("realized_range_points"),
        "atm_iv_change": delta("atm_iv"),
        "expected_move_change_points": delta("expected_move_points"),
        "pcr_change": delta("pcr"),
        "oi_change": delta("oi"),
        "option_spread_change_pct": delta("option_spread_pct"),
        "strategy_pnl_impact": payload.get("strategy_pnl_impact"),
    }

    return {
        "status": "BUILT",
        "panel_id": panel_id(
            event_id=payload["event_id"],
            instrument=payload["instrument"],
            observation_window_minutes=window,
        ),
        "panel": panel,
        "decision_eligibility_asserted": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="event-outcome-research",
        description="Build bounded event outcome research panel.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Build event outcome panel")
    build.add_argument("--input", required=True, help="Path to reviewed JSON payload")
    build.add_argument("--enabled", action="store_true", help="Enable research")
    build.add_argument(
        "--observation-window-minutes",
        type=int,
        default=60,
        help="Maximum observation window",
    )
    build.add_argument(
        "--max-payload-bytes",
        type=int,
        default=65536,
        help="Maximum payload size",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "build":
        parser.error("unsupported command")

    input_path = Path(args.input)
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

    settings = EventOutcomeResearchSettings(
        enabled=args.enabled,
        observation_window_minutes=args.observation_window_minutes,
        max_payload_bytes=args.max_payload_bytes,
    )
    result = build_event_outcome_panel(payload=payload, settings=settings)
    print(json.dumps(result, sort_keys=True, default=str))
    return 0 if result.get("status") == "BUILT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
