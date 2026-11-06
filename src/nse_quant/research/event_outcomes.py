"""Event-outcome research panel.

Joins retained event-impact evidence with observed event reactions to evaluate
whether pre-event synthesis was useful. This is research evidence only; it does
not authorize execution or create a decision gate.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EventOutcomePanelSettings(BaseModel):
    adverse_return_threshold_pct: float = -1.0
    iv_crush_threshold: float = -0.02
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


def classify_outcome(
    reaction: dict[str, Any],
    settings: EventOutcomePanelSettings,
) -> str:
    spot_return = reaction.get("spot_return_pct")
    if spot_return is None:
        return "INSUFFICIENT_DATA"
    if spot_return <= settings.adverse_return_threshold_pct:
        return "ADVERSE_MOVE"
    iv_change = reaction.get("atm_iv_change")
    if iv_change is not None and iv_change <= settings.iv_crush_threshold:
        return "IV_CRUSH"
    return "OBSERVED"


def build_event_outcomes(
    conn: Any,
    settings: EventOutcomePanelSettings | None = None,
) -> list[dict[str, Any]]:
    settings = settings or EventOutcomePanelSettings()
    rows = conn.execute(
        """
        SELECT
            e.impact_id,
            e.event_id,
            e.instrument,
            e.direction,
            e.volatility_impact,
            e.confidence,
            e.recommended_action,
            r.reaction_id,
            r.observation_window_minutes,
            r.spot_return_pct,
            r.realized_range_points,
            r.atm_iv_change,
            r.expected_move_change_points,
            r.pcr_change,
            r.relevant_oi_change,
            r.option_spread_change_pct
        FROM event_impact_evidence e
        JOIN event_reactions r
          ON r.event_id = e.event_id
         AND r.instrument = e.instrument
        ORDER BY e.event_id, e.instrument, r.observation_window_minutes
        """
    ).fetchall()

    outcomes = []
    for row in rows:
        reaction = {
            "spot_return_pct": row[9],
            "atm_iv_change": row[11],
        }
        outcomes.append(
            {
                "impact_id": row[0],
                "event_id": row[1],
                "instrument": row[2],
                "direction": row[3],
                "volatility_impact": row[4],
                "confidence": row[5],
                "recommended_action": row[6],
                "reaction_id": row[7],
                "observation_window_minutes": row[8],
                "spot_return_pct": row[9],
                "realized_range_points": row[10],
                "atm_iv_change": row[11],
                "expected_move_change_points": row[12],
                "pcr_change": row[13],
                "relevant_oi_change": row[14],
                "option_spread_change_pct": row[15],
                "outcome": classify_outcome(reaction, settings),
            }
        )
    return outcomes


def summarize(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    by_outcome: dict[str, int] = {}
    by_action: dict[str, int] = {}
    spot_returns = [
        item["spot_return_pct"] for item in outcomes if item["spot_return_pct"] is not None
    ]

    for item in outcomes:
        by_outcome[item["outcome"]] = by_outcome.get(item["outcome"], 0) + 1
        action = item["recommended_action"] or "UNKNOWN"
        by_action[action] = by_action.get(action, 0) + 1

    mean_spot_return = sum(spot_returns) / len(spot_returns) if spot_returns else None
    return {
        "total_outcomes": len(outcomes),
        "by_outcome": by_outcome,
        "by_recommended_action": by_action,
        "mean_spot_return_pct": mean_spot_return,
    }
