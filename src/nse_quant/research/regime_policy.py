"""Canonical-label train-only policy selection for walk-forward validation."""

from __future__ import annotations

from dataclasses import dataclass

from nse_quant.core.regime_registry import (
    is_canonical_regime_label,
    validate_regime_labels,
)
from nse_quant.research.trade_outcomes import TradeOutcome

MIN_TRAIN_TRADES_PER_REGIME = 10
MIN_TRAIN_AVG_PNL = 0.0


@dataclass(frozen=True)
class RegimePolicy:
    allowed_regimes: frozenset[str]
    regime_metrics: dict[str, dict[str, float | int]]
    selection_status: str

    @property
    def is_usable(self) -> bool:
        return (
            self.selection_status == "READY"
            and all(is_canonical_regime_label(label) for label in self.allowed_regimes)
            and all(is_canonical_regime_label(label) for label in self.regime_metrics)
        )

    def allows(self, regime: str | None) -> bool:
        if not self.is_usable or not is_canonical_regime_label(regime):
            return False
        return regime in self.allowed_regimes


def summarize_by_regime(
    outcomes: list[TradeOutcome],
) -> dict[str, dict[str, float | int]]:
    """Summarize canonical training outcomes without translating old labels.

    Mixed or legacy-labelled input is rejected as a whole, rather than silently
    filtering trades or assigning historical P&L to a new regime taxonomy.
    """
    validate_regime_labels(
        [outcome.regime for outcome in outcomes],
        context="training_outcomes.regime",
    )
    grouped: dict[str, list[TradeOutcome]] = {}
    for outcome in outcomes:
        grouped.setdefault(outcome.regime, []).append(outcome)

    metrics: dict[str, dict[str, float | int]] = {}
    for regime, regime_outcomes in grouped.items():
        trade_count = len(regime_outcomes)
        pnl = sum(outcome.realized_pnl for outcome in regime_outcomes)
        wins = sum(outcome.realized_pnl > 0 for outcome in regime_outcomes)
        gross_profit = sum(
            outcome.realized_pnl for outcome in regime_outcomes if outcome.realized_pnl > 0
        )
        gross_loss = sum(
            abs(outcome.realized_pnl) for outcome in regime_outcomes if outcome.realized_pnl < 0
        )
        metrics[regime] = {
            "trades": trade_count,
            "wins": wins,
            "pnl": pnl,
            "avg_pnl": pnl / trade_count if trade_count else 0.0,
            "win_rate": wins / trade_count if trade_count else 0.0,
            "profit_factor": (
                gross_profit / gross_loss if gross_loss else float("inf") if gross_profit else 0.0
            ),
        }
    return metrics


def select_regime_policy(
    outcomes: list[TradeOutcome],
    *,
    min_trades: int = MIN_TRAIN_TRADES_PER_REGIME,
    min_avg_pnl: float = MIN_TRAIN_AVG_PNL,
) -> RegimePolicy:
    """Select canonical regimes using training outcomes only."""
    regime_metrics = summarize_by_regime(outcomes)
    allowed = {
        regime
        for regime, metrics in regime_metrics.items()
        if int(metrics["trades"]) >= min_trades and float(metrics["avg_pnl"]) > min_avg_pnl
    }
    if not outcomes:
        return RegimePolicy(
            allowed_regimes=frozenset(),
            regime_metrics={},
            selection_status="INSUFFICIENT_TRAIN_DATA",
        )
    return RegimePolicy(
        allowed_regimes=frozenset(allowed),
        regime_metrics=regime_metrics,
        selection_status="READY",
    )
