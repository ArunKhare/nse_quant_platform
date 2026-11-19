r"""Bounded CLI for event-risk policy evaluation.

Reads a reviewed JSON payload and evaluates the event-risk policy. This CLI
never asserts event truth, never grants decision eligibility, and never enables
live trading.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from nse_quant.risk.event_risk_policy import (
    EventRiskPolicySettings,
    evaluate_event_risk,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="event-risk-policy",
        description="Evaluate event-risk policy.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    evaluate = sub.add_parser("evaluate", help="Evaluate event-risk policy")
    evaluate.add_argument("--input", required=True, help="Path to reviewed JSON payload")
    evaluate.add_argument("--enabled", action="store_true", help="Enable policy")
    evaluate.add_argument(
        "--reduce-size-on-high-volatility",
        action="store_true",
        help="Reduce size on high volatility",
    )
    evaluate.add_argument(
        "--max-size-reduction-pct",
        type=float,
        default=50.0,
        help="Maximum size reduction percentage",
    )
    evaluate.add_argument(
        "--review-iv-crush-threshold",
        type=float,
        default=-0.02,
        help="IV crush review threshold",
    )
    return parser


def run_evaluate(
    *,
    payload: dict[str, Any],
    settings: EventRiskPolicySettings,
) -> dict[str, Any]:
    event_impact = payload.get("event_impact")
    reaction = payload.get("reaction")

    if event_impact is not None and not isinstance(event_impact, dict):
        return {
            "status": "REJECTED",
            "reason": "event_impact_must_be_object",
            "decision_eligibility_asserted": False,
        }

    if reaction is not None and not isinstance(reaction, dict):
        return {
            "status": "REJECTED",
            "reason": "reaction_must_be_object",
            "decision_eligibility_asserted": False,
        }

    decision = evaluate_event_risk(
        event_impact=event_impact,
        reaction=reaction,
        settings=settings,
    )
    return {
        "status": "EVALUATED",
        "action": decision.action,
        "size_multiplier": decision.size_multiplier,
        "reasons": decision.reasons,
        "decision_eligibility_asserted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "evaluate":
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

    settings = EventRiskPolicySettings(
        enabled=args.enabled,
        reduce_size_on_high_volatility=args.reduce_size_on_high_volatility,
        max_size_reduction_pct=args.max_size_reduction_pct,
        review_iv_crush_threshold=args.review_iv_crush_threshold,
    )
    result = run_evaluate(payload=payload, settings=settings)
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("status") == "EVALUATED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
