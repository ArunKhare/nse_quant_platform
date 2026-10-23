"""Base contracts for decision-evidence plugins."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class DecisionContext:
    run_id: str
    symbol: str
    ts: datetime
    features: Any
    snapshot: Any
    iv_history_count: int
    current_regime: str | None
    effective_regimes: list[str]
    regime_policy: dict[str, Any] | None
    spot_instrument_token: int


class EvidencePlugin(Protocol):
    name: str

    def build(self, context: DecisionContext) -> dict[str, Any]:
        """Build one observational evidence payload."""
