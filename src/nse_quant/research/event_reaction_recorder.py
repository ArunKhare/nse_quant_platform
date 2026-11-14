"""Event-impact outcome reaction recorder; research-only persistence, no execution authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class EventReaction:
    impact_id: str
    run_id: str
    ts: datetime
    event_id: str
    event_type: str
    instrument: str
    spot_return_5m_pct: float | None
    spot_return_15m_pct: float | None
    spot_return_30m_pct: float | None
    spot_return_60m_pct: float | None
    realized_range: float | None
    atm_iv_change: float | None
    expected_move_change: float | None
    pcr_change: float | None
    oi_change: float | None
    option_spread_change: float | None
    strategy_pnl_impact: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "impact_id": self.impact_id,
            "run_id": self.run_id,
            "ts": self.ts.isoformat(),
            "event_id": self.event_id,
            "event_type": self.event_type,
            "instrument": self.instrument,
            "spot_return_5m_pct": self.spot_return_5m_pct,
            "spot_return_15m_pct": self.spot_return_15m_pct,
            "spot_return_30m_pct": self.spot_return_30m_pct,
            "spot_return_60m_pct": self.spot_return_60m_pct,
            "realized_range": self.realized_range,
            "atm_iv_change": self.atm_iv_change,
            "expected_move_change": self.expected_move_change,
            "pcr_change": self.pcr_change,
            "oi_change": self.oi_change,
            "option_spread_change": self.option_spread_change,
            "strategy_pnl_impact": self.strategy_pnl_impact,
            "decision_eligibility_asserted": False,
        }


TABLE = "event_reactions"
COLUMNS = (
    "impact_id",
    "run_id",
    "ts",
    "event_id",
    "event_type",
    "instrument",
    "spot_return_5m_pct",
    "spot_return_15m_pct",
    "spot_return_30m_pct",
    "spot_return_60m_pct",
    "realized_range",
    "atm_iv_change",
    "expected_move_change",
    "pcr_change",
    "oi_change",
    "option_spread_change",
    "strategy_pnl_impact",
)


def initialize_event_reactions(target: Any) -> None:
    target.execute(
        f"CREATE TABLE IF NOT EXISTS {TABLE} ("
        "impact_id VARCHAR PRIMARY KEY,"
        "run_id VARCHAR NOT NULL,"
        "ts TIMESTAMPTZ NOT NULL,"
        "event_id VARCHAR NOT NULL,"
        "event_type VARCHAR NOT NULL,"
        "instrument VARCHAR NOT NULL,"
        "spot_return_5m_pct DOUBLE,"
        "spot_return_15m_pct DOUBLE,"
        "spot_return_30m_pct DOUBLE,"
        "spot_return_60m_pct DOUBLE,"
        "realized_range DOUBLE,"
        "atm_iv_change DOUBLE,"
        "expected_move_change DOUBLE,"
        "pcr_change DOUBLE,"
        "oi_change DOUBLE,"
        "option_spread_change DOUBLE,"
        "strategy_pnl_impact DOUBLE)"
    )


def record_event_reaction(target: Any, reaction: EventReaction) -> dict[str, Any]:
    """Persist one observed post-event market reaction; idempotent by impact_id."""
    if target.execute(
        f"SELECT 1 FROM {TABLE} WHERE impact_id=? LIMIT 1", [reaction.impact_id]
    ).fetchone():
        return {
            "status": "ALREADY_RECORDED",
            "impact_id": reaction.impact_id,
            "decision_eligibility_asserted": False,
        }
    values = [getattr(reaction, name) for name in COLUMNS]
    placeholders = ",".join("?" for _ in COLUMNS)
    target.execute(
        f"INSERT INTO {TABLE} VALUES ({placeholders})",
        values,
    )
    return {
        "status": "RECORDED",
        "impact_id": reaction.impact_id,
        "decision_eligibility_asserted": False,
    }


def read_event_reactions(
    reader: Any, *, event_id: str | None = None, instrument: str | None = None
) -> list[dict[str, Any]]:
    """Read-only query of recorded reactions, optionally filtered by event_id or instrument."""
    sql = f"SELECT {','.join(COLUMNS)} FROM {TABLE}"
    conditions = []
    params: list[Any] = []
    if event_id is not None:
        conditions.append("event_id=?")
        params.append(event_id)
    if instrument is not None:
        conditions.append("instrument=?")
        params.append(instrument)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY ts"
    rows = reader.execute(sql, params).fetchall()
    return [dict(zip(COLUMNS, row, strict=True)) for row in rows]


def classify_reaction(reaction: EventReaction) -> str:
    """Classify a reaction as ADVERSE_MOVE, IV_CRUSH, OBSERVED, or INSUFFICIENT_DATA."""
    spot = reaction.spot_return_5m_pct
    iv = reaction.atm_iv_change
    if spot is None and iv is None:
        return "INSUFFICIENT_DATA"
    if spot is not None and spot < 0:
        return "ADVERSE_MOVE"
    if iv is not None and iv < 0:
        return "IV_CRUSH"
    return "OBSERVED"
