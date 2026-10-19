"""Regime-specific risk limits derived from training-fold outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nse_quant.research.regime_policy import RegimePolicy
from nse_quant.research.trade_outcomes import TradeOutcome


@dataclass(frozen=True)
class RegimeRiskLimits:
    regime: str
    allowed: bool
    max_lots_per_order: int
    max_open_positions: int
    max_notional_exposure: float
    max_portfolio_vega: float
    max_daily_loss: float
    reason: str


def build_regime_risk_limits(
    *,
    regime: str | None,
    policy: RegimePolicy,
    base_limits: Any,
) -> RegimeRiskLimits:
    """Return conservative limits for a regime.

    A regime must be explicitly allowed by a READY walk-forward policy.
    Unknown, unproven, or disallowed regimes receive no-entry limits.
    """
    if regime is None or not policy.allows(regime):
        return RegimeRiskLimits(
            regime=regime or "UNKNOWN",
            allowed=False,
            max_lots_per_order=0,
            max_open_positions=0,
            max_notional_exposure=0.0,
            max_portfolio_vega=0.0,
            max_daily_loss=0.0,
            reason=(
                "regime_not_allowed"
                if policy.is_usable
                else "policy_not_ready"
            ),
        )

    metrics = policy.regime_metrics.get(regime, {})
    trade_count = int(metrics.get("trades", 0))
    avg_pnl = float(metrics.get("avg_pnl", 0.0))
    profit_factor = float(metrics.get("profit_factor", 0.0))

    # Conservative scaling: full limits require strong training evidence.
    if trade_count >= 100 and profit_factor >= 1.25:
        scale = 1.0
        tier = "ROBUST"
    elif trade_count >= 30 and avg_pnl > 0:
        scale = 0.75
        tier = "USABLE"
    elif trade_count >= 10 and avg_pnl > 0:
        scale = 0.5
        tier = "INITIAL_EVIDENCE"
    else:
        return RegimeRiskLimits(
            regime=regime,
            allowed=False,
            max_lots_per_order=0,
            max_open_positions=0,
            max_notional_exposure=0.0,
            max_portfolio_vega=0.0,
            max_daily_loss=0.0,
            reason="insufficient_positive_evidence",
        )

    return RegimeRiskLimits(
        regime=regime,
        allowed=True,
        max_lots_per_order=max(
            1,
            int(base_limits.max_lots_per_order * scale),
        ),
        max_open_positions=max(
            1,
            int(base_limits.max_open_positions * scale),
        ),
        max_notional_exposure=(
            float(base_limits.max_notional_exposure) * scale
        ),
        max_portfolio_vega=(
            float(base_limits.max_portfolio_vega) * scale
        ),
        max_daily_loss=(
            float(base_limits.max_daily_loss) * scale
        ),
        reason=tier,
    )