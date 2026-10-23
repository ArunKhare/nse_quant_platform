from __future__ import annotations

from nse_quant.core.settings import (
    IronCondorProfileSettings,
    RegimePolicySettings,
)
from nse_quant.research.regime_policy_evaluation import (
    resolve_effective_regimes,
)


def make_profile() -> IronCondorProfileSettings:
    return IronCondorProfileSettings(
        enabled=True,
        strategy_type="iron_condor",
        regime_policy=RegimePolicySettings(
            allowed_regimes=[
                "NORMAL_IV_CONTANGO_NORMAL_SKEW",
                "NORMAL_IV_FLAT_TERM_NORMAL_SKEW",
            ],
            blocked_regimes=[
                "HIGH_IV_BACKWARDATION_HIGH_PUT_SKEW",
            ],
            require_iv_rank_available=True,
        ),
    )


def test_configured_policy_is_fallback_when_no_learned_policy():
    profile = make_profile()

    regimes, source, status = resolve_effective_regimes(
        profile,
        learned_policy=None,
    )

    assert source == "configured_profile"
    assert status is None
    assert regimes == [
        "NORMAL_IV_CONTANGO_NORMAL_SKEW",
        "NORMAL_IV_FLAT_TERM_NORMAL_SKEW",
    ]


def test_ready_learned_policy_overrides_configured_policy():
    profile = make_profile()

    regimes, source, status = resolve_effective_regimes(
        profile,
        learned_policy={
            "selection_status": "READY",
            "allowed_regimes": [
                "NORMAL_IV_CONTANGO_NORMAL_SKEW",
                "HIGH_IV_BACKWARDATION_HIGH_PUT_SKEW",
            ],
        },
    )

    assert source == "learned_policy"
    assert status == "READY"
    assert regimes == ["NORMAL_IV_CONTANGO_NORMAL_SKEW"]


def test_blocked_regime_is_removed_from_learned_policy():
    profile = make_profile()

    regimes, _, _ = resolve_effective_regimes(
        profile,
        learned_policy={
            "selection_status": "READY",
            "allowed_regimes": ["HIGH_IV_BACKWARDATION_HIGH_PUT_SKEW"],
        },
    )

    assert regimes == []
