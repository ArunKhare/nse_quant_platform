from __future__ import annotations

from nse_quant.core.settings import (
    IronCondorProfileSettings,
    RegimePolicySettings,
)
from nse_quant.research.regime_policy_evaluation import (
    resolve_effective_regimes,
)

H06 = "HIGH_IV_CONTANGO_NORMAL_SKEW_HIGH_VOL_CHOP"
H12 = "HIGH_IV_CONTANGO_HIGH_PUT_SKEW_HIGH_VOL_CHOP"
H24 = "HIGH_IV_FLAT_TERM_NORMAL_SKEW_HIGH_VOL_CHOP"
H42 = "HIGH_IV_BACKWARDATION_NORMAL_SKEW_HIGH_VOL_CHOP"


def make_profile(blocked: list[str] | None = None) -> IronCondorProfileSettings:
    return IronCondorProfileSettings(
        enabled=True,
        strategy_type="iron_condor",
        regime_policy=RegimePolicySettings(
            allowed_regimes=[H06, H24],
            blocked_regimes=blocked or [],
            require_iv_rank_available=True,
        ),
    )


def test_configured_policy_is_fallback_when_no_learned_policy():
    regimes, source, status = resolve_effective_regimes(make_profile(), learned_policy=None)

    assert source == "configured_profile"
    assert status is None
    assert regimes == sorted([H06, H24])


def test_ready_learned_policy_only_narrows_configured_policy():
    regimes, source, status = resolve_effective_regimes(
        make_profile(),
        learned_policy={"selection_status": "READY", "allowed_regimes": [H06, H12, H42]},
    )

    # H12 / H42 are not in the configured allowlist, so they cannot be added.
    assert source == "learned_policy_within_configured"
    assert status == "READY"
    assert regimes == [H06]


def test_learned_legacy_labels_are_ignored():
    regimes, _, _ = resolve_effective_regimes(
        make_profile(),
        learned_policy={"selection_status": "READY", "allowed_regimes": ["RANGE|HIGH", "BULL|NORMAL"]},
    )

    assert regimes == []


def test_blocked_regime_is_removed_from_learned_policy():
    regimes, _, _ = resolve_effective_regimes(
        make_profile(blocked=[H06]),
        learned_policy={"selection_status": "READY", "allowed_regimes": [H06]},
    )

    assert regimes == []
