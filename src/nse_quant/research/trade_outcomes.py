"""Join persisted decisions to realized trade outcomes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from nse_quant.core.regime_registry import is_canonical_regime_label


@dataclass(frozen=True)
class TradeOutcome:
    proposal_id: str
    underlying: str
    strategy: str
    regime: str
    opened_at: Any
    closed_at: Any
    realized_pnl: float
    regime_evidence_id: str | None = None
    regime_evidence_as_of: Any | None = None
    regime_evidence_status: str = "UNKNOWN"


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
            de.evidence_id,
            de.ts AS regime_evidence_as_of,
            JSON_EXTRACT_STRING(de.payload_json, '$.regime_label') AS regime,
            sp.strategy_position_id,
            sp.opened_at,
            sp.closed_at,
            ptr.realized_pnl
        FROM decisions d
        LEFT JOIN LATERAL (
            SELECT evidence.evidence_id, evidence.ts, evidence.payload_json
            FROM decision_evidence evidence
            WHERE evidence.run_id = d.run_id
              AND evidence.symbol = d.underlying
              AND evidence.plugin = 'institutional_regime'
              AND evidence.ts <= d.ts
            ORDER BY evidence.ts DESC
            LIMIT 1
        ) de ON TRUE
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

    for payload_json, evidence_id, evidence_as_of, regime, _, opened_at, closed_at, pnl in rows:
        payload = json.loads(payload_json) if payload_json else {}
        proposal = payload.get("proposal") or {}
        canonical = isinstance(regime, str) and is_canonical_regime_label(regime)
        outcomes.append(
            TradeOutcome(
                proposal_id=str(proposal.get("proposal_id")),
                underlying=symbol,
                strategy=str(proposal.get("strategy")),
                regime=regime if canonical else "UNKNOWN",
                opened_at=opened_at,
                closed_at=closed_at,
                realized_pnl=float(pnl or 0.0),
                regime_evidence_id=evidence_id,
                regime_evidence_as_of=evidence_as_of,
                regime_evidence_status=(
                    "CANONICAL_DECISION_TIME_EVIDENCE"
                    if canonical and evidence_id
                    else "MISSING_OR_NONCANONICAL_DECISION_TIME_EVIDENCE"
                ),
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
