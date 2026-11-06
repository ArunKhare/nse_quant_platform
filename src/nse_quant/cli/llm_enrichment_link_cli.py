"""Link retained LLM enrichment metadata to reviewed market events."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.llm_enrichment_links import (
    LLMEnrichmentEventLinker,
    LLMEnrichmentLinkSettings,
)

REQUIRED_FIELDS = (
    "enrichment_id",
    "event_id",
    "instrument",
    "event_ts",
    "observed_at",
)


def _rejected(reason: str, **details: Any) -> dict[str, Any]:
    return {
        "status": "REJECTED",
        "reason": reason,
        **details,
        "decision_eligibility_asserted": False,
    }


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def run_link(*, payload: object, linker: LLMEnrichmentEventLinker) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return _rejected("invalid_payload")

    missing = [
        field for field in REQUIRED_FIELDS if payload.get(field) is None or payload.get(field) == ""
    ]
    if missing:
        return _rejected("missing_required_fields", missing=missing)

    text_fields = ("enrichment_id", "event_id", "instrument")
    if any(not isinstance(payload[field], str) for field in text_fields):
        return _rejected("invalid_required_field")

    event_ts = _timestamp(payload["event_ts"])
    observed_at = _timestamp(payload["observed_at"])
    if event_ts is None or observed_at is None:
        return _rejected("invalid_timestamp")

    return linker.link(
        enrichment_id=payload["enrichment_id"],
        event_id=payload["event_id"],
        instrument=payload["instrument"],
        event_ts=event_ts,
        observed_at=observed_at,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    link = commands.add_parser("link", help="link an enrichment to a reviewed event")
    link.add_argument("--input", required=True, type=Path)
    link.add_argument("--enabled", action="store_true")
    link.add_argument("--max-link-window-minutes", type=int, default=60)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.input.is_file():
        print(json.dumps(_rejected("input_file_not_found"), sort_keys=True))
        return 2

    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        print(json.dumps(_rejected("invalid_input_file"), sort_keys=True))
        return 2

    if not isinstance(payload, dict):
        print(json.dumps(_rejected("invalid_input_file"), sort_keys=True))
        return 2

    settings = LLMEnrichmentLinkSettings(
        enabled=args.enabled,
        max_link_window_minutes=args.max_link_window_minutes,
    )
    store = DuckDBStore()
    try:
        linker = LLMEnrichmentEventLinker(store=store, settings=settings)
        result = run_link(payload=payload, linker=linker)
    finally:
        store.close()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"LINKED", "DUPLICATE"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
