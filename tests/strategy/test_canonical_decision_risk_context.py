"""Small critical tests for the actual installed decision-risk boundary."""

from __future__ import annotations

import ast
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from nse_quant.core.regime_registry import is_canonical_regime_label
from nse_quant.strategy.canonical_risk_context import (
    canonical_regime_for_risk,
    canonical_risk_rejection,
)

LABEL = "HIGH_IV_CONTANGO_NORMAL_SKEW_HIGH_VOL_CHOP"
ROOT = Path(__file__).resolve().parents[2]


def evidence():
    return {"institutional_regime": {"available": True, "complete": True, "regime_label": LABEL}}


def policy():
    return {
        "selection_status": "READY",
        "allowed_regimes": [LABEL],
        "risk_limits": {
            LABEL: {
                "allowed": True,
                "max_lots_per_order": 1,
                "max_open_positions": 1,
                "max_notional_exposure": 100000,
                "max_portfolio_vega": 1000,
                "max_daily_loss": 1000,
            }
        },
        "regime_metrics": {},
    }


def loop_method(name):
    path = ROOT / "src/nse_quant/strategy/decision_loop.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    cls = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "DecisionLoop")
    return copy.deepcopy(next(item for item in cls.body if isinstance(item, ast.FunctionDef) and item.name == name))


def test_canonical_complete_context_is_preserved():
    assert canonical_regime_for_risk(evidence()) == LABEL
    assert canonical_risk_rejection(LABEL, policy()) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"available": False},
        {"complete": False},
        {"complete": "true"},
        {"regime_label": "RANGE|HIGH"},
        {"thresholds_provisional": True},
        {"decision_eligibility_asserted": True},
    ],
)
def test_invalid_or_provisional_institutional_context_never_becomes_risk_key(changes):
    payload = evidence()
    payload["institutional_regime"].update(changes)
    assert canonical_regime_for_risk(payload) is None


def test_missing_institutional_context_has_no_daily_or_spot_fallback():
    assert canonical_regime_for_risk({"daily_regime": "BULL|NORMAL", "intraday_shape": "RANGE"}) is None


@pytest.mark.parametrize("status", ["STALE", "INSUFFICIENT_TRAIN_DATA", "UNKNOWN"])
def test_configured_limits_do_not_bypass_policy_readiness(status):
    payload = policy()
    payload["selection_status"] = status
    assert canonical_risk_rejection(LABEL, payload) == "policy_not_ready"


@pytest.mark.parametrize("field", ["risk_limits", "regime_metrics"])
def test_mixed_legacy_policy_keys_are_rejected_as_a_whole(field):
    payload = policy()
    payload[field]["RANGE|HIGH"] = {}
    assert canonical_risk_rejection(LABEL, payload) == "non_canonical_policy"


def test_allowlist_is_mandatory_and_must_explicitly_allow_current_label():
    payload = policy()
    payload["allowed_regimes"] = []
    assert canonical_risk_rejection(LABEL, payload) == "regime_not_allowed"
    payload["allowed_regimes"] = "RANGE|HIGH"
    assert canonical_risk_rejection(LABEL, payload) == "invalid_canonical_policy"
    assert canonical_risk_rejection(LABEL, None) == "policy_not_ready"


@pytest.mark.parametrize(
    "field,value",
    [
        ("allowed", "false"),
        ("max_daily_loss", float("nan")),
        ("max_notional_exposure", -1),
        ("max_lots_per_order", 1.5),
    ],
)
def test_malformed_configured_limits_fail_closed(field, value):
    payload = policy()
    payload["risk_limits"][LABEL][field] = value
    assert canonical_risk_rejection(LABEL, payload) == "invalid_configured_risk_limits"


def test_actual_run_once_risk_call_uses_institutional_evidence_not_legacy_local():
    method = loop_method("run_once")
    calls = [
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_apply_regime_limits"
    ]
    assert len(calls) == 1
    captured = []
    namespace = {
        "self": SimpleNamespace(_apply_regime_limits=lambda **kwargs: captured.append(kwargs)),
        "evidence": evidence(),
        "regime_policy": policy(),
        "current_regime": "RANGE|HIGH",
        "canonical_regime_for_risk": canonical_regime_for_risk,
    }
    isolated = ast.fix_missing_locations(ast.Module(body=[ast.Expr(value=calls[0])], type_ignores=[]))
    exec(compile(isolated, "actual_run_once_risk_call", "exec"), namespace)
    assert captured[0]["current_regime"] == LABEL
    assert captured[0]["regime_policy"] is namespace["regime_policy"]
    namespace["evidence"]["institutional_regime"]["thresholds_provisional"] = True
    exec(compile(isolated, "actual_run_once_risk_call", "exec"), namespace)
    assert captured[-1]["current_regime"] == "UNKNOWN"


def test_actual_risk_method_rejects_before_reading_configured_limits():
    method = loop_method("_apply_regime_limits")
    method.returns = None
    for argument in (*method.args.posonlyargs, *method.args.args, *method.args.kwonlyargs):
        argument.annotation = None
    namespace = {
        "canonical_risk_rejection": canonical_risk_rejection,
        "is_canonical_regime_label": is_canonical_regime_label,
        "RegimeRiskLimits": SimpleNamespace,
    }
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    exec(compile(module, "actual_apply_regime_limits", "exec"), namespace)
    payload = policy()
    payload["selection_status"] = "STALE"
    limits = namespace["_apply_regime_limits"](SimpleNamespace(), current_regime=LABEL, regime_policy=payload)
    assert not limits.allowed and limits.reason == "policy_not_ready"
    for field in (
        "max_lots_per_order",
        "max_open_positions",
        "max_notional_exposure",
        "max_portfolio_vega",
        "max_daily_loss",
    ):
        assert getattr(limits, field) == 0
