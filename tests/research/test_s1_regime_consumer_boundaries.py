from types import SimpleNamespace
from typing import Any, cast

from nse_quant.core.regime_registry import REGIMES
from nse_quant.strategy.canonical_risk_context import canonical_regime_for_risk
from nse_quant.strategy.decision_loop import DecisionLoop

CANONICAL, OTHER_CANONICAL = list(REGIMES)[:2]


def _eligible_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "available": True,
        "complete": True,
        "thresholds_provisional": False,
        "decision_eligibility_asserted": False,
        "regime_label": CANONICAL,
    }
    payload.update(overrides)
    return {"institutional_regime": payload}


def test_risk_context_requires_explicit_approval_metadata() -> None:
    evidence = _eligible_payload()
    assert canonical_regime_for_risk(evidence) == CANONICAL

    missing_provisional = _eligible_payload()
    del cast(dict[str, Any], missing_provisional["institutional_regime"])["thresholds_provisional"]
    assert canonical_regime_for_risk(missing_provisional) is None

    missing_assertion = _eligible_payload()
    del cast(dict[str, Any], missing_assertion["institutional_regime"])["decision_eligibility_asserted"]
    assert canonical_regime_for_risk(missing_assertion) is None


def test_risk_context_rejects_provisional_or_incomplete_evidence() -> None:
    assert canonical_regime_for_risk(_eligible_payload(thresholds_provisional=True)) is None
    assert canonical_regime_for_risk(_eligible_payload(complete=False)) is None
    assert canonical_regime_for_risk(_eligible_payload(available=False)) is None


def test_eligibility_audit_requires_all_classifier_readiness_flags() -> None:
    payload = {
        "available": True,
        "complete": True,
        "thresholds_provisional": False,
        "decision_eligibility_asserted": False,
        "regime_label": CANONICAL,
    }
    audit = DecisionLoop._institutional_regime_audit({"institutional_regime": payload})
    assert audit["regime_label_canonical"] is True
    assert audit["regime_label_eligible"] is True

    payload["thresholds_provisional"] = True
    audit = DecisionLoop._institutional_regime_audit({"institutional_regime": payload})
    assert audit["regime_label_canonical"] is True
    assert audit["regime_label_eligible"] is False


def test_static_risk_fallback_rejects_canonical_regime_outside_profile_allowlist() -> None:
    profile = SimpleNamespace(
        regime_policy=SimpleNamespace(
            allowed_regimes={CANONICAL},
            blocked_regimes=set(),
        )
    )
    settings = SimpleNamespace(
        get_strategy_profile=lambda _strategy_id: profile,
        get_effective_risk_settings=lambda _strategy_id: None,
    )
    loop = object.__new__(DecisionLoop)
    loop.settings = settings

    limits = loop._apply_regime_limits(
        current_regime=OTHER_CANONICAL,
        regime_policy=None,
    )

    assert limits.allowed is False
    assert limits.max_lots_per_order == 0
    assert limits.reason == "regime_not_in_configured_allowlist"
