from types import SimpleNamespace

from nse_quant.research.regime_policy import RegimePolicy
from nse_quant.research.regime_risk_policy import (
    build_regime_risk_limits,
)


def make_policy(
    allowed: set[str],
    metrics: dict[str, dict[str, float | int]],
) -> RegimePolicy:
    return RegimePolicy(
        allowed_regimes=frozenset(allowed),
        regime_metrics=metrics,
        selection_status="READY",
    )


def test_disallowed_regime_receives_no_entry_limits() -> None:
    policy = make_policy(
        allowed={"RANGE|HIGH"},
        metrics={
            "RANGE|HIGH": {
                "trades": 100,
                "avg_pnl": 10,
                "profit_factor": 1.5,
            }
        },
    )

    limits = build_regime_risk_limits(
        regime="BEAR|HIGH",
        policy=policy,
        base_limits=SimpleNamespace(
            max_lots_per_order=2,
            max_open_positions=3,
            max_notional_exposure=1_000_000,
            max_portfolio_vega=5_000,
            max_daily_loss=25_000,
        ),
    )

    assert limits.allowed is False
    assert limits.max_lots_per_order == 0


def test_usable_regime_receives_reduced_limits() -> None:
    policy = make_policy(
        allowed={"RANGE|HIGH"},
        metrics={
            "RANGE|HIGH": {
                "trades": 35,
                "avg_pnl": 10,
                "profit_factor": 1.1,
            }
        },
    )

    limits = build_regime_risk_limits(
        regime="RANGE|HIGH",
        policy=policy,
        base_limits=SimpleNamespace(
            max_lots_per_order=2,
            max_open_positions=3,
            max_notional_exposure=1_000_000,
            max_portfolio_vega=5_000,
            max_daily_loss=25_000,
        ),
    )

    assert limits.allowed is True
    assert limits.max_lots_per_order == 1
    assert limits.max_notional_exposure == 750_000


def test_robust_regime_receives_full_limits() -> None:
    policy = make_policy(
        allowed={"RANGE|HIGH"},
        metrics={
            "RANGE|HIGH": {
                "trades": 120,
                "avg_pnl": 10,
                "profit_factor": 1.4,
            }
        },
    )

    limits = build_regime_risk_limits(
        regime="RANGE|HIGH",
        policy=policy,
        base_limits=SimpleNamespace(
            max_lots_per_order=2,
            max_open_positions=3,
            max_notional_exposure=1_000_000,
            max_portfolio_vega=5_000,
            max_daily_loss=25_000,
        ),
    )

    assert limits.allowed is True
    assert limits.max_lots_per_order == 2
    assert limits.max_notional_exposure == 1_000_000
