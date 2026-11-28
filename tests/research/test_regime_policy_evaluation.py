from types import SimpleNamespace
from typing import Any, cast

from nse_quant.core.regime_registry import REGIMES
from nse_quant.research import regime_policy_evaluation as evaluation_module

REGIME = next(iter(REGIMES))


def test_configured_profile_fallback_is_not_learned_policy_actionable(monkeypatch) -> None:
    profile = SimpleNamespace(
        enabled=True,
        regime_policy=SimpleNamespace(
            allowed_regimes={REGIME},
            blocked_regimes=set(),
        ),
    )
    settings = SimpleNamespace(
        storage=SimpleNamespace(db_path="unused-test-database"),
        get_strategy_profile=lambda _strategy_id: profile,
    )
    connection = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(
        evaluation_module.duckdb,
        "connect",
        lambda *_args, **_kwargs: connection,
    )
    monkeypatch.setattr(evaluation_module, "load_trade_outcomes", lambda *_args, **_kwargs: [])

    result, outcomes = evaluation_module.evaluate_regime_policy(
        cast(Any, settings),
        symbol="NIFTY",
        strategy_id="iron_condor_monitor",
        start_date="2026-01-01",
        end_date="2026-01-31",
    )

    assert outcomes == []
    assert result.reason == "configured_policy_fallback"
    assert result.effective_allowed_regimes == [REGIME]
    assert result.actionable is False
