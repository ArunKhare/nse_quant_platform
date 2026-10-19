from datetime import date

from nse_quant.research.regime_policy import (
    RegimePolicy,
    select_regime_policy,
)
from nse_quant.research.trade_outcomes import TradeOutcome


def make_outcome(regime: str, pnl: float) -> TradeOutcome:
    return TradeOutcome(
        proposal_id=f"proposal-{regime}-{pnl}",
        underlying="NIFTY",
        strategy="iron_condor_monitor",
        regime=regime,
        opened_at=None,
        closed_at=None,
        realized_pnl=pnl,
    )


def test_regime_requires_minimum_trades_and_positive_pnl() -> None:
    outcomes = [
        make_outcome("RANGE|HIGH", 100)
        for _ in range(10)
    ] + [
        make_outcome("BULL|NORMAL", -50)
        for _ in range(10)
    ]

    policy = select_regime_policy(outcomes)

    assert policy.is_usable
    assert "RANGE|HIGH" in policy.allowed_regimes
    assert "BULL|NORMAL" not in policy.allowed_regimes


def test_insufficient_regime_history_is_not_allowed() -> None:
    outcomes = [make_outcome("RANGE|HIGH", 100)]

    policy = select_regime_policy(outcomes)

    assert policy.is_usable
    assert policy.allowed_regimes == frozenset()


def test_empty_training_data_is_unusable() -> None:
    policy = select_regime_policy([])

    assert not policy.is_usable
    assert policy.allowed_regimes == frozenset()
    assert policy.selection_status == "INSUFFICIENT_TRAIN_DATA"


def test_policy_allowlist_check() -> None:
    policy = RegimePolicy(
        allowed_regimes=frozenset({"RANGE|HIGH"}),
        regime_metrics={},
        selection_status="READY",
    )

    assert policy.allows("RANGE|HIGH")
    assert not policy.allows("BEAR|HIGH")
def test_stale_policy_is_not_actionable() -> None:
    policy = {
        "allowed_regimes": {"RANGE|HIGH"},
        "selection_status": "STALE",
        "test_end": date(2026, 1, 1),
    }

    current_regime = "RANGE|HIGH"

    policy_allows = (
        policy is not None
        and policy["selection_status"] == "READY"
        and current_regime in policy["allowed_regimes"]
    )

    assert policy_allows is False


def test_combined_regime_label_is_required() -> None:
    market_regime = {"regime": "RANGE|HIGH"}
    allowed = {"RANGE|HIGH"}

    assert market_regime["regime"] in allowed