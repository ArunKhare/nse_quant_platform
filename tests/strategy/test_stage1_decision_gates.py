"""Stage 1 decision-loop integration: timing filter, VRP gate, regime, audit.

Paper-only: every loop uses PaperBroker and an isolated temporary store.
"""

from __future__ import annotations

from typing import Any

import pytest

from nse_quant.core.evidence import EvidenceMode
from nse_quant.core.regime_registry import REGIME_REGISTRY_VERSION
from nse_quant.market_data.replay_provider import ReplayMarketDataProvider
from nse_quant.research.evidence_plugins.registry import EvidenceResult
from nse_quant.research.variance_risk_premium import VRP_CALCULATION_VERSION
from tests.conftest import SPOT_TOKEN, seed_daily_candles

H06 = "HIGH_IV_CONTANGO_NORMAL_SKEW_HIGH_VOL_CHOP"

MISALIGNED_TREND = {
    "available": True,
    "complete": True,
    "alignment": "MIXED",
    "timeframes": {
        "15m": {"trend": "UP", "change": 0.004},
        "60m": {"trend": "DOWN", "change": -0.006},
    },
}


def _loop(env, replay, **kwargs):
    provider = ReplayMarketDataProvider(replay["snapshots"])
    return env.build_loop(provider, proposal=replay["proposal"], approve_regime_risk=True, **kwargs)


def _inject_evidence(monkeypatch, loop, plugin: str, payload: dict[str, Any]) -> None:
    original = loop.evidence_runner.run

    def run(context):
        results = [result for result in original(context) if result.plugin != plugin]
        results.append(EvidenceResult(plugin=plugin, available=True, complete=True, payload=payload))
        return results

    monkeypatch.setattr(loop.evidence_runner, "run", run)


def _profile(loop):
    return loop.settings.get_strategy_profile("iron_condor_monitor")


def _evidence_plugins(loop) -> set[str]:
    rows = loop.store.conn.execute(
        "SELECT DISTINCT plugin FROM decision_evidence WHERE run_id = ?",
        [loop.run_id],
    ).fetchall()
    return {row[0] for row in rows}


# --- audit / persistence -----------------------------------------------------


def test_paper_fill_retains_stage1_audit_fields(decision_loop_environment, replay_snapshots):
    loop = _loop(decision_loop_environment, replay_snapshots)

    result = loop.run_once()

    assert result["status"] == "paper_filled"
    audit = result["decision_audit"]
    assert audit["decision_outcome"] == "paper_filled"
    assert audit["regime"]["regime_registry_version"] == REGIME_REGISTRY_VERSION
    assert "classifier_version" in audit["regime"]
    assert audit["realized_volatility_input"]["method"] == "trailing_close_to_close_daily"
    assert audit["realized_volatility_input"]["interval"] == "day"
    assert audit["variance_risk_premium"]["calculation_version"] == VRP_CALCULATION_VERSION
    assert audit["variance_risk_premium"]["gate_passed"] is True
    assert audit["timing_filter"]["filter_version"] == "multi_timeframe_timing_v1"
    assert "institutional_regime" in audit["evidence_provenance"]
    assert audit["paper_trading"] is True
    assert audit["decision_eligibility_asserted"] is False
    assert result["timing_filter"]["filter_version"] == "multi_timeframe_timing_v1"


def test_derived_and_plugin_evidence_are_persisted(decision_loop_environment, replay_snapshots):
    loop = _loop(decision_loop_environment, replay_snapshots)

    loop.run_once()

    plugins = _evidence_plugins(loop)
    assert {"timing_filter", "variance_risk_premium", "institutional_regime"} <= plugins


# --- VRP gate ----------------------------------------------------------------


def test_unavailable_vrp_rejects_before_paper_order(decision_loop_environment, replay_snapshots):
    loop = _loop(decision_loop_environment, replay_snapshots)
    loop.store.conn.execute("DELETE FROM spot_candles WHERE interval = 'day'")

    result = loop.run_once()

    assert result["status"] == "vrp_gate_rejected"
    assert result["rejection_reason"] == "variance_risk_premium_unavailable"
    assert result["variance_risk_premium"]["available"] is False
    assert loop.positions.get_open_strategy_positions() == []


def test_negative_vrp_rejects_before_paper_order(decision_loop_environment, replay_snapshots):
    loop = _loop(decision_loop_environment, replay_snapshots)
    loop.store.conn.execute("DELETE FROM spot_candles WHERE interval = 'day'")
    # ~5% daily moves -> annualized RV ~0.8, far above the fixture ATM IV.
    seed_daily_candles(loop.store, daily_move=0.05, instrument_token=SPOT_TOKEN)

    result = loop.run_once()

    assert result["status"] == "vrp_gate_rejected"
    assert result["rejection_reason"] == "variance_risk_premium_below_minimum"
    assert result["variance_risk_premium"]["variance_risk_premium"] < 0
    assert loop.positions.get_open_strategy_positions() == []


def test_vrp_rv_input_excludes_minute_realized_vol(decision_loop_environment, replay_snapshots):
    loop = _loop(decision_loop_environment, replay_snapshots)

    result = loop.run_once()

    vrp = result["variance_risk_premium"]
    assert vrp["expected_realized_volatility_input"]["source_table"] == "spot_candles"
    assert vrp["implied_volatility_input"]["source"] == "features.atm_iv"
    assert vrp["implied_volatility_input"]["constant_maturity_30d"] is False


# --- timing filter -----------------------------------------------------------


def test_observation_mode_misalignment_continues(monkeypatch, decision_loop_environment, replay_snapshots):
    loop = _loop(decision_loop_environment, replay_snapshots)
    _inject_evidence(monkeypatch, loop, "multi_timeframe_trend", MISALIGNED_TREND)

    result = loop.run_once()

    assert result["status"] == "paper_filled"
    assert result["timing_filter"]["mode"] == "observation"
    assert result["timing_filter"]["status"] == "OBSERVE"
    assert result["timing_filter"]["size_multiplier"] == 1.0
    assert "multi_timeframe_trend_misaligned" in result["timing_filter"]["reasons"]


def test_hard_gate_misalignment_rejects_before_paper_order(monkeypatch, decision_loop_environment, replay_snapshots):
    loop = _loop(decision_loop_environment, replay_snapshots)
    monkeypatch.setattr(_profile(loop).timing_filter, "mode", EvidenceMode.HARD_GATE)
    _inject_evidence(monkeypatch, loop, "multi_timeframe_trend", MISALIGNED_TREND)

    result = loop.run_once()

    assert result["status"] == "timing_filter_rejected"
    assert result["timing_filter"]["status"] == "BLOCK"
    assert loop.positions.get_open_strategy_positions() == []


def test_hard_gate_with_unavailable_trend_does_not_block(monkeypatch, decision_loop_environment, replay_snapshots):
    loop = _loop(decision_loop_environment, replay_snapshots)
    monkeypatch.setattr(_profile(loop).timing_filter, "mode", EvidenceMode.HARD_GATE)
    _inject_evidence(monkeypatch, loop, "multi_timeframe_trend", {"available": False})

    result = loop.run_once()

    assert result["status"] == "paper_filled"
    assert result["timing_filter"]["status"] == "OBSERVE"


def test_strategy_id_is_resolved_dynamically(monkeypatch, decision_loop_environment, replay_snapshots):
    loop = _loop(decision_loop_environment, replay_snapshots)
    alt = _profile(loop).model_copy(deep=True)
    monkeypatch.setitem(loop.settings.strategies, "iron_condor_alt", alt)
    monkeypatch.setattr(loop.settings.safety, "allowed_strategies", ["iron_condor_alt"])

    result = loop.run_once()

    assert result["timing_filter"]["strategy_id"] == "iron_condor_alt"
    assert result["variance_risk_premium"]["strategy_id"] == "iron_condor_alt"


def test_missing_timing_filter_falls_back_to_observation(monkeypatch, decision_loop_environment, replay_snapshots):
    loop = _loop(decision_loop_environment, replay_snapshots)
    original = loop._build_features

    def build_without_timing(*args, **kwargs):
        features, count, evidence = original(*args, **kwargs)
        evidence.pop("timing_filter", None)
        return features, count, evidence

    monkeypatch.setattr(loop, "_build_features", build_without_timing)

    result = loop.run_once()

    assert result["status"] == "paper_filled"
    assert result["timing_filter"]["mode"] == "observation"
    assert result["timing_filter"]["status"] == "OBSERVE"
    assert result["timing_filter"]["reasons"] == ["timing_filter_result_missing"]


def test_loop_feature_gate_has_no_implicit_trend_hard_gate(decision_loop_environment, replay_snapshots):
    loop = _loop(decision_loop_environment, replay_snapshots)

    assert loop.feature_gate._require_trend_alignment is False


# --- regime eligibility ------------------------------------------------------


def _institutional(label: str | None) -> dict[str, Any]:
    return {
        "available": True,
        "complete": label is not None,
        "classifier_version": "test_classifier",
        "regime_label": label,
    }


@pytest.mark.parametrize(
    "institutional_label,daily_regime,expected_allowed",
    [
        (H06, "BULL|NORMAL", True),
        # A canonical-looking daily regime must never be used for eligibility.
        ("NORMAL_IV_CONTANGO_NORMAL_SKEW_RANGE_MIDDLE", H06, False),
        (None, H06, False),
        ("HIGH_IV_BACKWARDATION_NORMAL_SKEW_HIGH_VOL_CHOP", "RANGE|HIGH", False),
    ],
)
def test_eligibility_uses_institutional_regime_label_only(
    monkeypatch,
    decision_loop_environment,
    replay_snapshots,
    institutional_label,
    daily_regime,
    expected_allowed,
):
    loop = _loop(decision_loop_environment, replay_snapshots, enforce_strategy_eligibility=True)
    _inject_evidence(monkeypatch, loop, "institutional_regime", _institutional(institutional_label))
    monkeypatch.setattr(loop.store, "get_market_regime_as_of", lambda **_kwargs: {"regime": daily_regime})

    captured: dict[str, Any] = {}
    original = loop._evaluate_strategy_eligibility

    def capture(**kwargs):
        captured.update(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(loop, "_evaluate_strategy_eligibility", capture)

    loop.run_once()

    assert captured["regime_allowed"] is expected_allowed
    assert captured["regime_source"] == "institutional_regime"
    assert captured["market_context_regime"] == daily_regime
    if not expected_allowed:
        assert captured["current_regime"] in {"UNKNOWN", institutional_label}


def test_stale_daily_closes_make_vrp_unavailable(decision_loop_environment, replay_snapshots):
    loop = _loop(decision_loop_environment, replay_snapshots)
    # Drop the most recent 10 days so the latest completed close is stale.
    loop.store.conn.execute(
        "DELETE FROM spot_candles WHERE interval = 'day' AND ts >= now() - INTERVAL 10 DAY"
    )

    result = loop.run_once()

    assert result["status"] == "vrp_gate_rejected"
    assert result["variance_risk_premium"]["expected_realized_volatility_input"]["reason"] == "stale_daily_closes"
    assert loop.positions.get_open_strategy_positions() == []


def test_kill_switch_blocks_before_evidence_and_paper_order(decision_loop_environment, replay_snapshots):
    loop = _loop(decision_loop_environment, replay_snapshots)
    loop.kill_switch.activate("stage1_test")

    result = loop.run_once()

    assert result["status"] == "kill_switch_active"
    assert _evidence_plugins(loop) == set()
    assert loop.positions.get_open_strategy_positions() == []
