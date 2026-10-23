from nse_quant.core.models import GateResult, MarketFeatures
from nse_quant.ops.live_snapshot import build_snapshot


def test_strategy_eligibility_is_included_in_snapshot():
    eligibility = GateResult(
        gate="strategy_eligibility",
        passed=False,
        reason="iv_regime_not_allowed",
        details={
            "current_regime": "UNKNOWN",
            "allowed_regimes": ["NORMAL_IV_CONTANGO_NORMAL_SKEW"],
        },
    )

    features = MarketFeatures(
        ts=__import__("datetime").datetime.now(__import__("datetime").UTC),
        underlying="NIFTY",
        spot=25000,
        expiry=__import__("datetime").date.today(),
    )

    snapshot = build_snapshot(
        features=features,
        loop_status="strategy_eligibility_rejected",
        strategy_eligibility=eligibility.model_dump(mode="json"),
    )

    assert snapshot["loop_status"] == "strategy_eligibility_rejected"
    assert snapshot["strategy_eligibility"]["passed"] is False
    assert snapshot["strategy_eligibility"]["reason"] == "iv_regime_not_allowed"


def test_strategy_eligibility_defaults_to_none():
    snapshot = build_snapshot()

    assert snapshot["strategy_eligibility"] is None
