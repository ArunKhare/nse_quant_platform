"""Small JSON snapshot for cross-process dashboard updates."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SNAPSHOT_PATH = Path("data/live_snapshot.json")


def write_live_snapshot(payload: dict[str, Any]) -> Path:
    """Atomically write the latest UI snapshot."""
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = SNAPSHOT_PATH.with_suffix(".json.tmp")

    temporary_path.write_text(
        json.dumps(payload, default=str, separators=(",", ":")),
        encoding="utf-8",
    )

    temporary_path.replace(SNAPSHOT_PATH)
    return SNAPSHOT_PATH


def read_live_snapshot() -> dict[str, Any]:
    """Read the latest UI snapshot. Returns an empty dict if unavailable."""
    if not SNAPSHOT_PATH.exists():
        return {}

    try:
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def build_snapshot(
    features: Any | None = None,
    open_positions: list[Any] | None = None,
    latest_orders: list[Any] | None = None,
    latest_exits: list[Any] | None = None,
    kill_switch_active: bool = False,
    loop_status: str = "idle",
) -> dict[str, Any]:
    return {
        "updated_at": datetime.now(UTC).isoformat(),
        "loop_status": loop_status,
        "kill_switch_active": kill_switch_active,
        "features": features.model_dump(mode="json") if features else None,
        "open_positions": [
            position.model_dump(mode="json")
            for position in (open_positions or [])
        ],
        "latest_orders": latest_orders or [],
        "latest_exits": latest_exits or [],
    }