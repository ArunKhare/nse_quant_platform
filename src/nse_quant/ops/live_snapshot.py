"""Small JSON snapshot for cross-process dashboard updates."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_SNAPSHOT_PATH = Path("data/live_snapshot.json")


def write_live_snapshot(payload: dict[str, Any], *, snapshot_path: Path | None = None) -> Path:
    """Atomically write the latest UI snapshot."""
    target = snapshot_path or DEFAULT_SNAPSHOT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = target.with_suffix(".json.tmp")

    temporary_path.write_text(
        json.dumps(payload, default=str, separators=(",", ":")),
        encoding="utf-8",
    )

    temporary_path.replace(target)
    return target


def read_live_snapshot(
    *,
    snapshot_path: Path | None = None,
) -> dict[str, Any]:
    """Read the latest UI snapshot. Returns an empty dict if unavailable."""
    target = snapshot_path or DEFAULT_SNAPSHOT_PATH
    if not target.exists():
        return {}

    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def build_snapshot(
    features: Any | None = None,
    open_positions: list[Any] | None = None,
    latest_orders: list[Any] | None = None,
    latest_exits: list[Any] | None = None,
    kill_switch_active: bool = False,
    loop_status: str = "idle",
    data_quality: dict[str, Any] | None = None,
    iv_history: dict[str, Any] | None = None,
    strategy_eligibility: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "updated_at": datetime.now(UTC).isoformat(),
        "loop_status": loop_status,
        "kill_switch_active": kill_switch_active,
        "features": features.model_dump(mode="json") if features else None,
        "open_positions": [position.model_dump(mode="json") for position in (open_positions or [])],
        "latest_orders": latest_orders or [],
        "latest_exits": latest_exits or [],
        "data_quality": data_quality
        or {
            "is_usable": True,
            "stale": False,
            "missing_quotes": 0,
            "missing_bid_ask": 0,
            "zero_volume_legs": 0,
            "issues": [],
            "warnings": [],
        },
        "iv_history": iv_history
        or {
            "observation_count": 0,
            "minimum_required": 0,
            "mode": "COLD_START",
        },
        "strategy_eligibility": strategy_eligibility,
    }
