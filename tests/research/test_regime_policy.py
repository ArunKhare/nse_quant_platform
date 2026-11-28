import pytest

from nse_quant.core.regime_registry import REGIMES, is_canonical_regime_label
from nse_quant.research.regime_policy import (
    RegimePolicy,
    select_regime_policy,
    summarize_by_regime,
)
from nse_quant.research.trade_outcomes import TradeOutcome

CANONICAL = "HIGH_IV_CONTANGO_NORMAL_SKEW_HIGH_VOL_CHOP"
OTHER_CANONICAL = "HIGH_IV_FLAT_TERM_NORMAL_SKEW_HIGH_VOL_CHOP"


def make_outcome(regime: str, pnl: float) -> TradeOutcome:
    return TradeOutcome(
        proposal_id=f"proposal-{regime}-{pnl}",
        underlying="NIFTY",
        strategy="iron_condor_monitor",
        regime=regime,
        opened_at=None,
        closed_at=None,
        realized_pnl=pnl,
        regime_evidence_status="CANONICAL_DECISION_TIME_EVIDENCE",
    )


def test_regime_requires_minimum_trades_and_positive_pnl() -> None:
    outcomes = [make_outcome(CANONICAL, 100) for _ in range(10)] + [
        make_outcome(OTHER_CANONICAL, -50) for _ in range(10)
    ]
    policy = select_regime_policy(outcomes)
    assert policy.is_usable
    assert policy.allowed_regimes == frozenset({CANONICAL})
    assert set(policy.regime_metrics) == {CANONICAL, OTHER_CANONICAL}
    assert all(is_canonical_regime_label(label) for label in policy.regime_metrics)


def test_insufficient_regime_history_is_not_allowed() -> None:
    policy = select_regime_policy([make_outcome(CANONICAL, 100)])
    assert policy.is_usable
    assert policy.allowed_regimes == frozenset()


def test_empty_training_data_is_unusable() -> None:
    policy = select_regime_policy([])
    assert not policy.is_usable
    assert policy.allowed_regimes == frozenset()
    assert policy.selection_status == "INSUFFICIENT_TRAIN_DATA"


def test_policy_allowlist_check() -> None:
    policy = RegimePolicy(frozenset({CANONICAL}), {}, "READY")
    assert policy.allows(CANONICAL)
    assert not policy.allows(OTHER_CANONICAL)
    assert not policy.allows(None)


def test_stale_policy_is_not_actionable() -> None:
    policy = RegimePolicy(frozenset({CANONICAL}), {}, "STALE")
    assert not policy.is_usable
    assert not policy.allows(CANONICAL)


@pytest.mark.parametrize("label", list(REGIMES))
def test_every_complete_canonical_label_is_supported(label: str) -> None:
    policy = RegimePolicy(frozenset({label}), {}, "READY")
    assert policy.allows(label)


@pytest.mark.parametrize(
    "legacy",
    [
        "RANGE|HIGH",
        "BULL|NORMAL",
        "BEAR|HIGH",
        "BULLISH",
        "BEARISH",
        "MIXED",
        "HIGH_IV_CONTANGO_NORMAL_SKEW_STRONG_BULL",
        "NORMAL_IV_CONTANGO_NORMAL_SKEW_RANGE_MIDDLE",
        "HIGH_IV_CONTANGO_NORMAL_SKEW_HIGH_VOL_CHOP_POSITIVE_VRP",
        "UNKNOWN",
        "",
    ],
)
def test_legacy_policy_cannot_authorize_any_label(legacy: str) -> None:
    policy = RegimePolicy(frozenset({CANONICAL, legacy}), {}, "READY")
    assert not policy.is_usable
    assert not policy.allows(legacy)
    assert not policy.allows(CANONICAL)


def test_legacy_metric_keys_make_policy_unusable() -> None:
    policy = RegimePolicy(
        frozenset({CANONICAL}), {"RANGE|HIGH": {"trades": 100}}, "READY"
    )
    assert not policy.is_usable
    assert not policy.allows(CANONICAL)


@pytest.mark.parametrize("selector", [select_regime_policy, summarize_by_regime])
def test_training_rejects_legacy_labels_instead_of_translating(selector) -> None:
    outcomes = [make_outcome("RANGE|HIGH", 100) for _ in range(10)]
    with pytest.raises(ValueError, match="training_outcomes.regime: non-canonical"):
        selector(outcomes)


@pytest.mark.parametrize("selector", [select_regime_policy, summarize_by_regime])
def test_mixed_training_input_is_not_silently_filtered(selector) -> None:
    outcomes = [make_outcome(CANONICAL, 100) for _ in range(10)]
    outcomes.append(make_outcome("RANGE|HIGH", -1000))
    with pytest.raises(ValueError, match="non-canonical"):
        selector(outcomes)


def test_canonical_summary_preserves_training_pnl() -> None:
    metrics = summarize_by_regime(
        [make_outcome(CANONICAL, 100), make_outcome(CANONICAL, -40)]
    )[CANONICAL]
    assert metrics["trades"] == 2
    assert metrics["wins"] == 1
    assert metrics["pnl"] == 60
    assert metrics["avg_pnl"] == 30
    assert metrics["win_rate"] == 0.5
    assert metrics["profit_factor"] == 2.5
