from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from nse_quant.research.regime_policy import RegimePolicy
from nse_quant.research.regime_risk_policy import (
    RegimeRiskLimits,
    build_regime_risk_limits,
)

CANONICAL = "HIGH_IV_CONTANGO_NORMAL_SKEW_HIGH_VOL_CHOP"
OTHER_CANONICAL = "HIGH_IV_FLAT_TERM_NORMAL_SKEW_HIGH_VOL_CHOP"


def make_policy(
    allowed: set[str],
    metrics: dict[str, dict[str, float | int]],
) -> RegimePolicy:
    return RegimePolicy(frozenset(allowed), metrics, "READY")


@pytest.fixture
def base_limits() -> SimpleNamespace:
    return SimpleNamespace(
        max_lots_per_order=2,
        max_open_positions=3,
        max_notional_exposure=1_000_000,
        max_portfolio_vega=5_000,
        max_daily_loss=25_000,
    )


def assert_no_entry(limits: RegimeRiskLimits) -> None:
    assert limits.allowed is False
    assert limits.max_lots_per_order == 0
    assert limits.max_open_positions == 0
    assert limits.max_notional_exposure == 0.0
    assert limits.max_portfolio_vega == 0.0
    assert limits.max_daily_loss == 0.0


def test_disallowed_canonical_regime_receives_no_entry_limits(
    base_limits: SimpleNamespace,
) -> None:
    limits = build_regime_risk_limits(
        regime=OTHER_CANONICAL,
        policy=make_policy({CANONICAL}, {}),
        base_limits=base_limits,
    )
    assert_no_entry(limits)
    assert limits.regime == OTHER_CANONICAL
    assert limits.reason == "regime_not_allowed"


@pytest.mark.parametrize(
    ("trades", "profit_factor", "scale", "tier"),
    [
        (10, 1.1, 0.5, "INITIAL_EVIDENCE"),
        (35, 1.1, 0.75, "USABLE"),
        (120, 1.4, 1.0, "ROBUST"),
    ],
)
def test_canonical_regime_preserves_existing_risk_tiers(
    base_limits: SimpleNamespace,
    trades: int,
    profit_factor: float,
    scale: float,
    tier: str,
) -> None:
    policy = make_policy(
        {CANONICAL},
        {CANONICAL: {"trades": trades, "avg_pnl": 10, "profit_factor": profit_factor}},
    )
    limits = build_regime_risk_limits(
        regime=CANONICAL, policy=policy, base_limits=base_limits
    )
    assert limits.allowed is True
    assert limits.regime == CANONICAL
    assert limits.reason == tier
    assert limits.max_lots_per_order == max(1, int(2 * scale))
    assert limits.max_open_positions == max(1, int(3 * scale))
    assert limits.max_notional_exposure == 1_000_000 * scale
    assert limits.max_portfolio_vega == 5_000 * scale
    assert limits.max_daily_loss == 25_000 * scale


@pytest.mark.parametrize(
    "label",
    [
        "RANGE|HIGH",
        "BULL|NORMAL",
        "BEAR|HIGH",
        "BULLISH",
        "BEARISH",
        "MIXED",
        "HIGH_IV_CONTANGO_NORMAL_SKEW_STRONG_BULL",
        "HIGH_IV_CONTANGO_NORMAL_SKEW_HIGH_VOL_CHOP_POSITIVE_VRP",
        "UNKNOWN",
        "",
    ],
)
def test_noncanonical_input_is_rejected_before_policy_lookup(
    base_limits: SimpleNamespace, label: str
) -> None:
    policy = Mock(spec=RegimePolicy)
    policy.allows.return_value = True
    limits = build_regime_risk_limits(
        regime=label, policy=policy, base_limits=base_limits
    )
    assert_no_entry(limits)
    assert limits.regime == "UNKNOWN"
    assert limits.reason == "non_canonical_regime"
    policy.allows.assert_not_called()


def test_missing_regime_is_rejected_before_policy_lookup(
    base_limits: SimpleNamespace,
) -> None:
    policy = Mock(spec=RegimePolicy)
    limits = build_regime_risk_limits(
        regime=None, policy=policy, base_limits=base_limits
    )
    assert_no_entry(limits)
    assert limits.reason == "regime_unavailable"
    policy.allows.assert_not_called()


def test_nonready_policy_still_blocks_canonical_regime(
    base_limits: SimpleNamespace,
) -> None:
    policy = RegimePolicy(frozenset({CANONICAL}), {}, "INSUFFICIENT_TRAIN_DATA")
    limits = build_regime_risk_limits(
        regime=CANONICAL, policy=policy, base_limits=base_limits
    )
    assert_no_entry(limits)
    assert limits.reason == "policy_not_ready"


def test_insufficient_canonical_training_evidence_still_blocks(
    base_limits: SimpleNamespace,
) -> None:
    policy = make_policy(
        {CANONICAL}, {CANONICAL: {"trades": 9, "avg_pnl": 10, "profit_factor": 2.0}}
    )
    limits = build_regime_risk_limits(
        regime=CANONICAL, policy=policy, base_limits=base_limits
    )
    assert_no_entry(limits)
    assert limits.reason == "insufficient_positive_evidence"


def test_legacy_policy_cannot_supply_risk_for_canonical_input(
    base_limits: SimpleNamespace,
) -> None:
    policy = make_policy(
        {CANONICAL, "RANGE|HIGH"},
        {CANONICAL: {"trades": 120, "avg_pnl": 10, "profit_factor": 1.4}},
    )
    limits = build_regime_risk_limits(
        regime=CANONICAL, policy=policy, base_limits=base_limits
    )
    assert_no_entry(limits)
    assert limits.reason == "policy_not_ready"
