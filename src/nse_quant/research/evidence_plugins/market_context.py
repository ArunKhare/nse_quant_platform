"""Point-in-time observational context from persisted index regimes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from nse_quant.core.settings import MarketContextSettings
from nse_quant.research.evidence_plugins.base import (
    DecisionContext,
    EvidencePlugin,
)


class MarketContextPlugin(EvidencePlugin):
    name = "market_context"

    def __init__(
        self,
        *,
        store: Any,
        settings: MarketContextSettings,
    ) -> None:
        self._store = store
        self._settings = settings

    def build(self, context: DecisionContext) -> dict[str, Any]:
        as_of = self._utc(context.ts)

        indices = {
            symbol: self._index_context(
                symbol=symbol,
                as_of=as_of,
            )
            for symbol in self._settings.symbols
        }

        available = any(result["available"] for result in indices.values())
        complete = all(result["complete"] for result in indices.values())

        if complete:
            reason = None
        elif available:
            reason = "incomplete_context"
        else:
            reason = "no_context_observations"

        return {
            "available": available,
            "complete": complete,
            "as_of": as_of.isoformat(),
            "symbol": context.symbol,
            "source": "market_regimes",
            "classifier_version": "persisted_index_context_v1",
            "max_age_seconds": self._settings.max_age_seconds,
            "context_indices": indices,
            "reason": reason,
        }

    def _index_context(
        self,
        *,
        symbol: str,
        as_of: datetime,
    ) -> dict[str, Any]:
        row = self._store.conn.execute(
            """
            SELECT
                ts,
                trend_regime,
                volatility_regime,
                iv_regime,
                regime
            FROM market_regimes
            WHERE symbol = ?
              AND ts <= ?
            ORDER BY ts DESC
            LIMIT 1
            """,
            [symbol, as_of],
        ).fetchone()

        if row is None:
            return {
                "available": False,
                "complete": False,
                "observation_ts": None,
                "age_seconds": None,
                "regime": None,
                "trend_regime": None,
                "volatility_regime": None,
                "iv_regime": None,
                "reason": "no_point_in_time_regime",
            }

        observation_ts = self._utc(row[0])
        age_seconds = (as_of - observation_ts).total_seconds()

        if age_seconds < 0:
            raise ValueError("Market context query returned a future observation")

        regime = row[4]
        usable_regime = (
            isinstance(regime, str) and bool(regime.strip()) and regime.strip().upper() != "UNKNOWN"
        )
        stale = age_seconds > self._settings.max_age_seconds

        if stale:
            reason = "stale_regime"
        elif not usable_regime:
            reason = "unknown_regime"
        else:
            reason = None

        return {
            "available": True,
            "complete": reason is None,
            "observation_ts": observation_ts.isoformat(),
            "age_seconds": age_seconds,
            "regime": regime,
            "trend_regime": row[1],
            "volatility_regime": row[2],
            "iv_regime": row[3],
            "reason": reason,
        }

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Market context requires timezone-aware timestamps")

        return value.astimezone(UTC)
