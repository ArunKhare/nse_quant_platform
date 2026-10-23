"""Join persisted decisions to realized trade outcomes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class TradeOutcome:
    proposal_id: str
    underlying: str
    strategy: str
    regime: str
    opened_at: Any
    closed_at: Any
    realized_pnl: float


def load_trade_outcomes(
    conn: Any,
    *,
    symbol: str,
    start_date: date,
    end_date: date,
) -> list[TradeOutcome]:
    rows = conn.execute(
        """
        SELECT
            d.payload,
            r.regime,
            sp.strategy_position_id,
            sp.opened_at,
            sp.closed_at,
            ptr.realized_pnl
        FROM decisions d
        LEFT JOIN market_regimes r
          ON r.symbol = d.underlying
         AND r.ts = (
             SELECT MAX(regime.ts)
             FROM market_regimes regime
             WHERE regime.symbol = d.underlying
               AND regime.ts <= d.ts
         )
        JOIN strategy_positions sp
          ON sp.proposal_id = JSON_EXTRACT_STRING(
              d.payload,
              '$.proposal.proposal_id'
          )
        JOIN post_trade_reviews ptr
          ON ptr.strategy_position_id = sp.strategy_position_id
        WHERE d.underlying = ?
          AND d.decision_type IN ('dry_run', 'paper_filled')
          AND CAST(sp.opened_at AS DATE) >= ?
          AND CAST(sp.closed_at AS DATE) <= ?
          AND sp.status = 'CLOSED'
        ORDER BY sp.opened_at
        """,
        [symbol, start_date, end_date],
    ).fetchall()

    outcomes: list[TradeOutcome] = []

    for payload_json, regime, _, opened_at, closed_at, pnl in rows:
        payload = json.loads(payload_json) if payload_json else {}

        proposal = payload.get("proposal") or {}

        outcomes.append(
            TradeOutcome(
                proposal_id=str(proposal.get("proposal_id")),
                underlying=symbol,
                strategy=str(proposal.get("strategy")),
                regime=regime or "UNKNOWN",
                opened_at=opened_at,
                closed_at=closed_at,
                realized_pnl=float(pnl or 0.0),
            )
        )

    return outcomes


def summarize_outcomes(
    outcomes: list[TradeOutcome],
) -> dict[str, Any]:
    trade_count = len(outcomes)
    pnl = sum(outcome.realized_pnl for outcome in outcomes)
    wins = sum(outcome.realized_pnl > 0 for outcome in outcomes)
    gross_profit = sum(outcome.realized_pnl for outcome in outcomes if outcome.realized_pnl > 0)
    gross_loss = sum(abs(outcome.realized_pnl) for outcome in outcomes if outcome.realized_pnl < 0)

    return {
        "trades": trade_count,
        "wins": wins,
        "pnl": pnl,
        "win_rate": wins / trade_count if trade_count else 0.0,
        "avg_pnl": pnl / trade_count if trade_count else 0.0,
        "profit_factor": (
            gross_profit / gross_loss if gross_loss else float("inf") if gross_profit else 0.0
        ),
    }
