r"""Bounded CLI for event impact synthesis validation.

Reads a reviewed JSON payload and validates a bounded event impact synthesis
against observed outcome. This CLI never asserts event truth, never grants
decision eligibility, and never enables live trading.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class EventImpactSynthesisValidationSettings(BaseModel):
    enabled: bool = False
    max_payload_bytes: int = Field(default=65536, ge=1)


def validation_id(
    *,
    synthesis_id: str,
    event_id: str,
    instrument: str,
) -> str:
    canonical = json.dumps(
        {
            "synthesis_id": synthesis_id,
            "event_id": event_id,
            "instrument": instrument,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def validate_event_impact_synthesis(
    *,
    payload: dict[str, Any],
    settings: EventImpactSynthesisValidationSettings,
) -> dict[str, Any]:
    if not settings.enabled:
        return {
            "status": "REJECTED",
            "reason": "event_impact_synthesis_validation_disabled",
            "decision_eligibility_asserted": False,
        }

    required = (
        "synthesis_id",
        "event_id",
        "instrument",
        "decision_ts",
        "evidence",
        "outcome",
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

    evidence = payload["evidence"]
    outcome = payload["outcome"]
    if not isinstance(evidence, dict) or not isinstance(outcome, dict):
        return {
            "status": "REJECTED",
            "reason": "evidence_and_outcome_must_be_objects",
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

    def numeric(value: Any) -> float | None:
        return float(value) if isinstance(value, (int, float)) else None

    spot_return = numeric(outcome.get("spot_return_pct"))
    iv_change = numeric(outcome.get("atm_iv_change"))
    expected_move_change = numeric(outcome.get("expected_move_change_points"))

    volatility_impact = evidence.get("volatility_impact")
    high_volatility = volatility_impact == "high"
    large_move = spot_return is not None and abs(spot_return) >= 1.0
    iv_crush = (
        iv_change is not None
        and expected_move_change is not None
        and iv_change < 0.0
        and expected_move_change < 0.0
    )

    useful = (high_volatility and large_move) or (not high_volatility and not large_move)

    validation = {
        "plugin": "event_impact_synthesis_validation",
        "available": True,
        "synthesis_id": payload["synthesis_id"],
        "event_id": payload["event_id"],
        "instrument": payload["instrument"],
        "decision_ts": decision_ts.isoformat(),
        "spot_return_pct": spot_return,
        "atm_iv_change": iv_change,
        "expected_move_change_points": expected_move_change,
        "high_volatility": high_volatility,
        "large_move": large_move,
        "iv_crush": iv_crush,
        "useful": useful,
    }

    return {
        "status": "VALIDATED",
        "validation_id": validation_id(
            synthesis_id=payload["synthesis_id"],
            event_id=payload["event_id"],
            instrument=payload["instrument"],
        ),
        "validation": validation,
        "decision_eligibility_asserted": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="event-impact-synthesis-validation",
        description="Validate bounded event impact synthesis.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate event impact synthesis")
    validate.add_argument("--input", required=True, help="Path to reviewed JSON payload")
    validate.add_argument("--enabled", action="store_true", help="Enable validation")
    validate.add_argument(
        "--max-payload-bytes",
        type=int,
        default=65536,
        help="Maximum payload size",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "validate":
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

    settings = EventImpactSynthesisValidationSettings(
        enabled=args.enabled,
        max_payload_bytes=args.max_payload_bytes,
    )
    result = validate_event_impact_synthesis(payload=payload, settings=settings)
    print(json.dumps(result, sort_keys=True, default=str))
    return 0 if result.get("status") == "VALIDATED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
