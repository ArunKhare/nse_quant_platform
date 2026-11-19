r"""Bounded CLI for event outcome panel.

Builds a bounded event outcome research panel from captured event reactions.
This CLI never asserts event truth, never grants decision eligibility, and
never enables live trading.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from nse_quant.persistence.duckdb_store import DuckDBStore


class EventOutcomePanelSettings(BaseModel):
    enabled: bool = False
    max_rows: int = Field(default=1000, ge=1)


def build_event_outcome_panel(
    *,
    store: Any,
    settings: EventOutcomePanelSettings,
    event_id: str,
    instrument: str,
) -> dict[str, Any]:
    if not settings.enabled:
        return {
            "status": "REJECTED",
            "reason": "event_outcome_panel_disabled",
            "decision_eligibility_asserted": False,
        }

    rows = store.conn.execute(
        """
        SELECT reaction_id, event_id, instrument, captured_at, payload
        FROM event_reactions
        WHERE event_id = ? AND instrument = ?
        ORDER BY captured_at
        LIMIT ?
        """,
        [event_id, instrument, settings.max_rows],
    ).fetchall()

    panel_rows = []
    complete_count = 0
    for reaction_id, event_id_row, instrument_row, captured_at, payload in rows:
        payload_dict = json.loads(payload) if isinstance(payload, str) else payload
        complete = payload_dict.get("complete", False)
        if complete:
            complete_count += 1
        panel_rows.append(
            {
                "reaction_id": reaction_id,
                "event_id": event_id_row,
                "instrument": instrument_row,
                "captured_at": captured_at.isoformat()
                if hasattr(captured_at, "isoformat")
                else captured_at,
                "complete": complete,
                "payload": payload_dict,
            }
        )

    return {
        "status": "BUILT",
        "event_id": event_id,
        "instrument": instrument,
        "row_count": len(panel_rows),
        "complete_count": complete_count,
        "rows": panel_rows,
        "decision_eligibility_asserted": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="event-outcome-panel",
        description="Build event outcome research panel.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Build event outcome panel")
    build.add_argument("--db", required=True, help="Path to DuckDB database")
    build.add_argument("--event-id", required=True, help="Event ID")
    build.add_argument("--instrument", required=True, help="Instrument symbol")
    build.add_argument("--enabled", action="store_true", help="Enable panel build")
    build.add_argument("--max-rows", type=int, default=1000, help="Maximum rows")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "build":
        parser.error("unsupported command")

    db_path = Path(args.db)
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

    settings = EventOutcomePanelSettings(
        enabled=args.enabled,
        max_rows=args.max_rows,
    )
    store = DuckDBStore(db_path)
    result = build_event_outcome_panel(
        store=store,
        settings=settings,
        event_id=args.event_id,
        instrument=args.instrument,
    )
    print(json.dumps(result, sort_keys=True, default=str))
    store.conn.close()
    return 0 if result.get("status") == "BUILT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
