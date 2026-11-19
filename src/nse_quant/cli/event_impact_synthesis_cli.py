r"""Bounded CLI for event impact synthesis.

Reads a reviewed JSON payload and synthesizes bounded event impact evidence for
an instrument. This CLI never asserts event truth, never grants decision
eligibility, and never enables live trading.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class EventImpactSynthesisSettings(BaseModel):
    enabled: bool = False
    block_new_entries: bool = False
    max_payload_bytes: int = Field(default=65536, ge=1)


def synthesis_id(
    *,
    event_id: str,
    instrument: str,
    decision_ts: datetime,
) -> str:
    canonical = json.dumps(
        {
            "event_id": event_id,
            "instrument": instrument,
            "decision_ts": decision_ts.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def synthesize_event_impact(
    *,
    payload: dict[str, Any],
    settings: EventImpactSynthesisSettings,
) -> dict[str, Any]:
    if not settings.enabled:
        return {
            "status": "REJECTED",
            "reason": "event_impact_synthesis_disabled",
            "decision_eligibility_asserted": False,
        }

    required = (
        "event_id",
        "instrument",
        "decision_ts",
        "mapping",
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

    mapping = payload["mapping"]
    if not isinstance(mapping, dict):
        return {
            "status": "REJECTED",
            "reason": "mapping_must_be_object",
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

    confidence = mapping.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0):
        confidence = None

    action = (
        "BLOCK_NEW_ENTRIES"
        if settings.block_new_entries and mapping.get("volatility_impact") == "high"
        else "OBSERVE"
    )

    evidence = {
        "plugin": "event_impact",
        "available": True,
        "event_id": payload["event_id"],
        "instrument": payload["instrument"],
        "decision_ts": decision_ts.isoformat(),
        "direction": mapping.get("direction", "CONDITIONAL"),
        "volatility_impact": mapping.get("volatility_impact", "MEDIUM"),
        "liquidity_impact": mapping.get("liquidity_impact", "MEDIUM"),
        "confidence": confidence,
        "surprise": payload.get("surprise"),
        "recommended_action": action,
        "reason": "event_impact_synthesized",
    }

    return {
        "status": "SYNTHESIZED",
        "synthesis_id": synthesis_id(
            event_id=payload["event_id"],
            instrument=payload["instrument"],
            decision_ts=decision_ts,
        ),
        "evidence": evidence,
        "decision_eligibility_asserted": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="event-impact-synthesis",
        description="Synthesize bounded event impact evidence.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    synthesize = sub.add_parser("synthesize", help="Synthesize event impact")
    synthesize.add_argument("--input", required=True, help="Path to reviewed JSON payload")
    synthesize.add_argument("--enabled", action="store_true", help="Enable synthesis")
    synthesize.add_argument(
        "--block-new-entries",
        action="store_true",
        help="Enable new-entry blackout",
    )
    synthesize.add_argument(
        "--max-payload-bytes",
        type=int,
        default=65536,
        help="Maximum payload size",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "synthesize":
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

    settings = EventImpactSynthesisSettings(
        enabled=args.enabled,
        block_new_entries=args.block_new_entries,
        max_payload_bytes=args.max_payload_bytes,
    )
    result = synthesize_event_impact(payload=payload, settings=settings)
    print(json.dumps(result, sort_keys=True, default=str))
    return 0 if result.get("status") == "SYNTHESIZED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
