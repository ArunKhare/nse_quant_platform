"""Test Evidence Multi-Time Frame implementation"""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from nse_quant.features.availability import FeatureAvailability, FeatureAvailabilityReport
from nse_quant.market_data.replay_provider import ReplayMarketDataProvider
from nse_quant.research.candle_resampler import (
    latest_completed_candles,
)
from nse_quant.research.evidence_plugins.base import DecisionContext, EvidencePlugin
from nse_quant.research.evidence_plugins.registry import EvidencePluginRunner


def make_candle(minute: int, close: float) -> dict:
    return {
        "date": datetime(2026, 10, 22, 9, minute),
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": 100,
    }


def test_fifteen_minute_bucket_requires_complete_candles():
    candles = [make_candle(minute, 100 + minute) for minute in range(15)]

    completed = latest_completed_candles(
        candles,
        interval_minutes=15,
        limit=10,
    )

    assert completed == []


def test_completed_fifteen_minute_bucket_is_resampled():
    candles = []

    for minute in range(16):
        candles.append(make_candle(minute, 100 + minute))

    completed = latest_completed_candles(
        candles,
        interval_minutes=15,
        limit=10,
    )

    assert len(completed) == 1
    assert completed[0].open == 100
    assert completed[0].close == 114
    assert completed[0].high == 115
    assert completed[0].low == 99
    assert completed[0].candle_count == 15


def test_evidence_results_are_persisted(
    decision_loop_environment,
    replay_snapshots,
    test_settings,
):
    test_settings.evidence.enabled = True
    test_settings.evidence.plugins.multi_timeframe.enabled = True
    test_settings.evidence.plugins.multi_timeframe.timeframes = ["1m"]
    snapshot = replay_snapshots["snapshots"][0]
    provider = ReplayMarketDataProvider(replay_snapshots["snapshots"])
    loop = decision_loop_environment.build_loop(provider)
    loop.kill_switch = Mock()
    loop.kill_switch.is_active.return_value = False
    loop.availability_checker = Mock()
    loop.availability_checker.evaluate.return_value = FeatureAvailabilityReport(
        symbol=snapshot.underlying,
        as_of=datetime.now(UTC),
        core_status=FeatureAvailability.READY,
        htf_status=FeatureAvailability.READY,
        iv_status=FeatureAvailability.READY,
        overall_status=FeatureAvailability.READY,
        observations={},
        missing=[],
        reasons=[],
    )
    loop.settings.research.enforce_strategy_eligibility = False

    end = snapshot.ts.replace(second=0, microsecond=0)
    candles = []
    for minute_offset in range(61):
        close = 23000.0 + minute_offset
        candles.append(
            {
                "date": end - timedelta(minutes=60 - minute_offset),
                "open": close,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": 1000,
            }
        )
    loop.store.write_spot_candles(
        candles=candles,
        symbol=snapshot.underlying,
        instrument_token=256265,
        interval="1m",
    )

    result = loop.run_once()
    print(result["status"])

    rows = loop.store.conn.execute(
        """
        SELECT plugin, available, payload_json
        FROM decision_evidence
        WHERE run_id = ?
        """,
        [loop.run_id],
    ).fetchall()

    assert len(rows) == 1
    plugin, available, payload_json = rows[0]
    payload = json.loads(payload_json)
    assert plugin == "multi_timeframe_trend"
    assert available is True
    assert payload["complete"] is True
    assert payload["alignment"] == "BULLISH"
    assert payload["timeframes"]["1m"] == {
        "trend": "UP",
        "completed_buckets": 60,
        "required_buckets": 60,
        "complete": True,
    }


def test_runner_returns_typed_evidence_results():
    plugin = Mock(spec=EvidencePlugin)
    plugin.name = "multi_timeframe_trend"
    plugin.build.return_value = {
        "available": True,
        "complete": True,
        "timeframes": {},
    }

    runner = EvidencePluginRunner([plugin])
    results = runner.run(make_context())

    assert len(results) == 1
    assert results[0].plugin == "multi_timeframe_trend"
    assert results[0].available is True
    assert results[0].complete is True


def test_runner_captures_plugin_failure():
    plugin = Mock(spec=EvidencePlugin)
    plugin.name = "multi_timeframe_trend"
    plugin.build.side_effect = RuntimeError("boom")

    runner = EvidencePluginRunner([plugin])
    results = runner.run(make_context())

    assert len(results) == 1
    assert results[0].available is False
    assert results[0].complete is False
    assert results[0].payload["error_type"] == "RuntimeError"


def test_persisting_evidence_updates_the_existing_result(test_store):
    ts = datetime(2026, 10, 22, 9)
    key = {
        "run_id": "test-run",
        "ts": ts,
        "symbol": "NIFTY",
        "plugin": "multi_timeframe_trend",
    }
    test_store.write_decision_evidence(**key, evidence={"available": True, "version": 1})
    test_store.write_decision_evidence(**key, evidence={"available": False, "version": 2})

    rows = test_store.conn.execute(
        """
        SELECT available, payload_json
        FROM decision_evidence
        WHERE run_id = ? AND ts = ? AND symbol = ? AND plugin = ?
        """,
        [key["run_id"], ts, key["symbol"], key["plugin"]],
    ).fetchall()

    assert len(rows) == 1
    available, payload_json = rows[0]
    assert available is False
    assert json.loads(payload_json) == {"available": False, "version": 2}


def make_context() -> DecisionContext:
    return DecisionContext(
        run_id="test-run",
        symbol="NIFTY",
        ts=datetime(2026, 10, 22, 9),
        features=None,
        snapshot=None,
        iv_history_count=0,
        current_regime=None,
        effective_regimes=[],
        regime_policy=None,
        spot_instrument_token=256265,
    )
