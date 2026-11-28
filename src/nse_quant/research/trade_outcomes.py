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
            de.payload_json AS regime_evidence_payload,
            sp.strategy_position_id,
            sp.opened_at,
            sp.closed_at,
            ptr.realized_pnl
        FROM decisions d
        LEFT JOIN decision_evidence de
          ON de.evidence_id = JSON_EXTRACT_STRING(
              d.payload,
              '$.decision_audit.regime.evidence_id'
          )
         AND de.run_id = d.run_id
         AND de.symbol = d.underlying
         AND de.plugin = 'institutional_regime'
         AND de.ts <= d.ts
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

    for payload_json, evidence_id, evidence_as_of, evidence_payload_json, _, opened_at, closed_at, pnl in rows:
        payload = json.loads(payload_json) if payload_json else {}
        evidence_payload = json.loads(evidence_payload_json) if evidence_payload_json else {}
        proposal = payload.get("proposal") or {}
        regime = evidence_payload.get("regime_label")
        if evidence_id is None:
            evidence_status = "MISSING_DECISION_TIME_EVIDENCE"
        elif evidence_payload.get("available") is not True:
            evidence_status = "REGIME_EVIDENCE_UNAVAILABLE"
        elif evidence_payload.get("complete") is not True:
            evidence_status = "REGIME_EVIDENCE_INCOMPLETE"
        elif evidence_payload.get("thresholds_provisional") is not False:
            evidence_status = "REGIME_THRESHOLDS_NOT_APPROVED"
        elif evidence_payload.get("decision_eligibility_asserted") is not False:
            evidence_status = "REGIME_ELIGIBILITY_METADATA_NOT_EXPLICITLY_FALSE"
        elif not is_canonical_regime_label(regime):
            evidence_status = "NONCANONICAL_DECISION_TIME_REGIME"
        else:
            evidence_status = "CANONICAL_DECISION_TIME_EVIDENCE"
        canonical = evidence_status == "CANONICAL_DECISION_TIME_EVIDENCE"
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
                regime_evidence_status=evidence_status,
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
