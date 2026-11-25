from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

from nse_quant.core.models import (
    ChainSnapshot,
    Instrument,
    OptionQuote,
    OptionType,
)
from nse_quant.core.settings import get_settings
from nse_quant.execution.broker import PaperBroker
from nse_quant.market_data.replay_provider import (
    ReplayMarketDataProvider,
)
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.har_realized_volatility import DailyRVObservation
from nse_quant.strategy import decision_loop as decision_loop_module
from nse_quant.strategy.decision_loop import DecisionLoop


class SyntheticProvider:
    def get_chain_snapshot(self):
        expiry = datetime.now(UTC).date() + timedelta(days=5)
        spot = 25000.0

        quotes = []

        # Two expiries satisfy settings.analytics.expiries_per_snapshot (2).
        next_expiry = expiry + timedelta(days=7)
        for leg_expiry, token_offset, strike, option_type in [
            (expiry, 0, 24600, OptionType.PE),
            (expiry, 0, 24800, OptionType.PE),
            (expiry, 0, 25200, OptionType.CE),
            (expiry, 0, 25400, OptionType.CE),
            (next_expiry, 100000, 24800, OptionType.PE),
            (next_expiry, 100000, 25200, OptionType.CE),
        ]:
            token = strike + token_offset
            instrument = Instrument(
                tradingsymbol=f"NIFTY{leg_expiry:%y%m%d}{strike}{option_type.value}",
                instrument_token=token,
                underlying="NIFTY",
                expiry=leg_expiry,
                strike=strike,
                option_type=option_type,
                lot_size=75,
            )

            quotes.append(
                OptionQuote(
                    instrument_token=token,
                    ltp=100.0,
                    bid=99.0,
                    ask=101.0,
                    volume=100000,
                    oi=100000,
                    instrument=instrument,
                    iv=0.15,
                )
            )

        return ChainSnapshot(
            underlying="NIFTY",
            spot=spot,
            expiry=expiry,
            quotes=quotes,
        )


def test_decision_loop_persists_feature_and_decision(
    tmp_path,
    seed_spot_features,
):
    store = DuckDBStore(tmp_path / "loop.duckdb")
    seed_spot_features(store)
    settings = get_settings()
    settings.research.enforce_feature_availability = False
    live_snapshot_path = tmp_path / "live_snapshot.json"
    loop = DecisionLoop(
        store=store,
        provider=SyntheticProvider(),
        broker=PaperBroker(),
        run_id="test-run",
        settings=settings,
        spot_instrument_token_resolver=lambda symbol: 256265,
        live_snapshot_path=live_snapshot_path,
    )
    loop.settings.research.enforce_strategy_eligibility = False
    try:
        result = loop.run_once()
        assert result["status"] in {
            "no_proposal",
            "risk_rejected",
            "dry_run",
            "strategy_eligibility_rejected",
            "vrp_gate_rejected",
        }
        if result["status"] == "vrp_gate_rejected":
            assert result["rejection_reason"] == (
                "variance_risk_premium_estimator_not_gate_eligible"
            )
            assert result["variance_risk_premium"]["estimator_gate_eligible"] is False

        feature_count = store.conn.execute("SELECT COUNT(*) FROM feature_snapshots").fetchone()[0]

        decision_count = store.conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]

        assert feature_count == 1
        assert decision_count >= 1
    finally:
        store.close()


def test_feature_gate_rejection_does_not_call_chain_provider(
    decision_loop,
    monkeypatch,
) -> None:
    provider_calls = 0
    get_chain_snapshot = decision_loop.provider.get_chain_snapshot

    def track_chain_snapshot():
        nonlocal provider_calls
        provider_calls += 1
        return get_chain_snapshot()

    monkeypatch.setattr(
        decision_loop.provider,
        "get_chain_snapshot",
        track_chain_snapshot,
    )
    monkeypatch.setattr(
        decision_loop.feature_service,
        "latest",
        lambda _symbol: None,
    )

    result = decision_loop.run_once()

    assert result["status"] == "feature_gate_rejected"
    assert result["reasons"] == ["spot_features_unavailable"]
    assert provider_calls == 0


def test_active_kill_switch_blocks_order_submission(
    decision_loop_environment,
    replay_snapshots,
    tmp_path,
    monkeypatch,
):
    provider = ReplayMarketDataProvider(replay_snapshots["snapshots"])
    loop = decision_loop_environment.build_loop(
        provider,
        proposal=replay_snapshots["proposal"],
        approve_regime_risk=True,
    )

    monkeypatch.setattr(
        loop,
        "kill_switch",
        SimpleNamespace(
            is_active=lambda: True,
            status=lambda: {
                "active": True,
                "reason": "test_kill_switch",
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ),
    )

    submit = Mock()
    monkeypatch.setattr(loop.broker, "submit", submit)

    result = loop.run_once()

    assert result["status"] == "kill_switch_active"
    assert result["kill_switch_active"] is True
    submit.assert_not_called()



def test_decision_loop_uses_calibrated_har_forecast_and_keeps_atm_iv_fail_closed(
    monkeypatch,
) -> None:
    settings = get_settings()
    snapshot_ts = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)
    session_day = snapshot_ts.date() - timedelta(days=1)
    observations = tuple(
        DailyRVObservation(
            session_date=session_day - timedelta(days=offset),
            overnight_return=0.001,
            intraday_variance=0.0002,
            realized_variance=0.000201,
            source_minute_rows=375,
            first_minute_ts=datetime.combine(
                session_day - timedelta(days=offset),
                datetime.min.time(),
                tzinfo=UTC,
            ),
            last_minute_ts=datetime.combine(
                session_day - timedelta(days=offset),
                datetime.min.time(),
                tzinfo=UTC,
            ),
        )
        for offset in range(350)
    )

    monkeypatch.setattr(
        decision_loop_module,
        "build_daily_rv_observations",
        lambda *_args, **_kwargs: observations,
    )
    monkeypatch.setattr(
        decision_loop_module,
        "forecast_har_rv_30d",
        lambda *_args, **_kwargs: (
            0.15,
            {"method": "har_rv_5m_intraday_plus_overnight", "reason": None},
        ),
    )
    monkeypatch.setattr(
        decision_loop_module,
        "calibrate_har_rv_forecast_errors",
        lambda *_args, **_kwargs: {
            "absolute_error_p90": 0.003,
            "samples": 60,
            "reason": None,
            "gate_margin_eligible": True,
            "diagnostic_only": False,
        },
    )

    class StoreStub:
        def completed_one_minute_candles(self, **_kwargs):
            return []

        def completed_daily_closes(self, **_kwargs):
            return []

    loop = object.__new__(DecisionLoop)
    loop.settings = settings
    loop.store = StoreStub()
    features = SimpleNamespace(atm_iv=0.20, ts=snapshot_ts)
    snapshot = SimpleNamespace(ts=snapshot_ts)

    result = loop._evaluate_vrp(
        strategy_id="iron_condor_monitor",
        features=features,
        snapshot=snapshot,
        instrument_token=256265,
    )

    assert result["expected_realized_volatility"] == 0.15
    assert result["forecast_error_margin"] == 0.003
    assert result["minimum_vrp"] == settings.get_strategy_profile(
        "iron_condor_monitor"
    ).vrp_gate.minimum_vrp + 0.003
    assert result["estimator_gate_eligible"] is True
    assert result["implied_volatility_gate_eligible"] is False
    assert result["gate_passed"] is False
    rv_input = result["expected_realized_volatility_input"]
    assert rv_input["gate_eligible"] is True
    assert rv_input["trailing_close_to_close_fallback"]["used_for_gate"] is False
