from types import SimpleNamespace

from nse_quant.core.models import MarketFeatures


def make_features(iv_rank=None):
    return MarketFeatures(
        ts=__import__("datetime").datetime.now(__import__("datetime").UTC),
        underlying="NIFTY",
        spot=25000,
        expiry=__import__("datetime").date.today(),
        iv_rank=iv_rank,
    )


def test_eligibility_rejects_unknown_regime(decision_loop_environment):
    loop = decision_loop_environment.build_loop(
        SimpleNamespace(),
        enforce_strategy_eligibility=True,
    )

    profile = loop.settings.get_strategy_profile("iron_condor_monitor")

    gate = loop._evaluate_strategy_eligibility(
        profile=profile,
        features=make_features(iv_rank=50),
        iv_history_count=50,
        current_regime="UNKNOWN",
        regime_allowed=False,
        regime_policy=None,
    )

    assert gate.passed is False
    assert gate.reason == "IV regime not allowed: UNKNOWN"


def test_eligibility_rejects_missing_iv_rank(
    decision_loop_environment,
):
    loop = decision_loop_environment.build_loop(
        SimpleNamespace(),
        enforce_strategy_eligibility=True,
    )

    profile = loop.settings.get_strategy_profile("iron_condor_monitor")

    allowed_regime = profile.regime_policy.allowed_regimes[0]

    gate = loop._evaluate_strategy_eligibility(
        profile=profile,
        features=make_features(iv_rank=None),
        iv_history_count=50,
        current_regime=allowed_regime,
        regime_allowed=True,
        regime_policy=None,
    )

    assert gate.passed is False
    assert gate.reason == "IV rank unavailable"
