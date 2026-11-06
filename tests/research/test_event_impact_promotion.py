"""Tests for the event impact promotion evaluator."""

from __future__ import annotations

from nse_quant.research.event_impact_promotion import (
    EventImpactPromotionSettings,
    evaluate_promotion,
)


def _outcome(outcome: str, spot_return: float | None = None) -> dict:
    return {"outcome": outcome, "spot_return_pct": spot_return}


def test_insufficient_events():
    settings = EventImpactPromotionSettings(min_events=10)
    outcomes = [_outcome("ADVERSE_MOVE", -2.0) for _ in range(5)]
    result = evaluate_promotion(
        outcomes=outcomes,
        regimes=["A", "B", "C"],
        settings=settings,
    )
    assert result["status"] == "NOT_PROMOTED"
    assert result["reason"] == "insufficient_events"


def test_insufficient_regimes():
    settings = EventImpactPromotionSettings(min_events=3, min_regimes=3)
    outcomes = [_outcome("ADVERSE_MOVE", -2.0) for _ in range(3)]
    result = evaluate_promotion(
        outcomes=outcomes,
        regimes=["A", "A"],
        settings=settings,
    )
    assert result["status"] == "NOT_PROMOTED"
    assert result["reason"] == "insufficient_regimes"


def test_insufficient_adverse_move_rate():
    settings = EventImpactPromotionSettings(
        min_events=3,
        min_adverse_move_rate=0.8,
        min_regimes=1,
    )
    outcomes = [
        _outcome("ADVERSE_MOVE", -2.0),
        _outcome("OBSERVED", 0.5),
        _outcome("OBSERVED", 0.5),
    ]
    result = evaluate_promotion(
        outcomes=outcomes,
        regimes=["A"],
        settings=settings,
    )
    assert result["status"] == "NOT_PROMOTED"
    assert result["reason"] == "insufficient_adverse_move_rate"


def test_insufficient_iv_crush_rate():
    settings = EventImpactPromotionSettings(
        min_events=3,
        min_adverse_move_rate=0.5,
        min_iv_crush_rate=0.5,
        min_regimes=1,
    )
    outcomes = [
        _outcome("ADVERSE_MOVE", -2.0),
        _outcome("ADVERSE_MOVE", -2.0),
        _outcome("OBSERVED", 0.5),
    ]
    result = evaluate_promotion(
        outcomes=outcomes,
        regimes=["A"],
        settings=settings,
    )
    assert result["status"] == "NOT_PROMOTED"
    assert result["reason"] == "insufficient_iv_crush_rate"


def test_mean_spot_return_above_threshold():
    settings = EventImpactPromotionSettings(
        min_events=3,
        min_adverse_move_rate=0.5,
        min_iv_crush_rate=0.3,
        max_mean_spot_return_pct=0.0,
        min_regimes=1,
    )
    outcomes = [
        _outcome("ADVERSE_MOVE", 1.0),
        _outcome("ADVERSE_MOVE", 1.0),
        _outcome("IV_CRUSH", 1.0),
    ]
    result = evaluate_promotion(
        outcomes=outcomes,
        regimes=["A"],
        settings=settings,
    )
    assert result["status"] == "NOT_PROMOTED"
    assert result["reason"] == "mean_spot_return_above_threshold"


def test_promotion_eligible():
    settings = EventImpactPromotionSettings(
        min_events=3,
        min_adverse_move_rate=0.5,
        min_iv_crush_rate=0.3,
        max_mean_spot_return_pct=0.0,
        min_regimes=1,
    )
    outcomes = [
        _outcome("ADVERSE_MOVE", -2.0),
        _outcome("ADVERSE_MOVE", -2.0),
        _outcome("IV_CRUSH", -1.0),
    ]
    result = evaluate_promotion(
        outcomes=outcomes,
        regimes=["A", "B"],
        settings=settings,
    )
    assert result["status"] == "PROMOTION_ELIGIBLE"
    assert result["decision_eligibility_asserted"] is False
