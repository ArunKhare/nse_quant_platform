"""Persistent kill switch."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


class KillSwitch:
    def __init__(self, path: str | Path | None = None) -> None:
        # settings = get_settings()
        self.path = Path(path or Path(".local/kill_switch.json"))
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, object]:
        if not self.path.exists():
            return {"active": False, "reason": None, "updated_at": None}

        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"active": False, "reason": None, "updated_at": None}

    def _write(self, active: bool, reason: str) -> None:
        self.path.write_text(
            json.dumps(
                {
                    "active": active,
                    "reason": reason,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ),
            encoding="utf-8",
        )

    def activate(self, reason: str = "manual_activation") -> None:
        self._write(True, reason)

    def reset(self, reason: str = "manual_reset") -> None:
        self._write(False, reason)

    def is_active(self) -> bool:
        return bool(self._read().get("active", False))

    def status(self) -> dict[str, object]:
        return self._read()