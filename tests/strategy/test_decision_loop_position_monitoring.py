from types import SimpleNamespace

from nse_quant.market_data.replay_provider import (
    ReplayMarketDataProvider,
)


def test_open_position_is_marked_and_exit_evaluated(
    decision_loop_environment,
    replay_snapshots,
):
    provider = ReplayMarketDataProvider(replay_snapshots["snapshots"])
    loop = decision_loop_environment.build_loop(
        provider,
        proposal=replay_snapshots["proposal"],
    )
    loop.settings.research.enforce_strategy_eligibility = False
    first = loop.run_once()
    assert first["status"] == "paper_filled"

    strategy_position_id = first["strategy_position_id"]

    second = loop.run_once()

    assert second["status"] in {
        "paper_filled",
        "max_open_positions",
    }

    outcomes = second["position_outcomes"]
    assert outcomes
    assert strategy_position_id in [outcome["strategy_position_id"] for outcome in outcomes]


def test_position_closes_when_exit_triggers(
    decision_loop_environment,
    exit_trigger_snapshots,
):
    provider = ReplayMarketDataProvider(exit_trigger_snapshots["snapshots"])
    loop = decision_loop_environment.build_loop(
        provider,
        proposal=exit_trigger_snapshots["proposal"],
    )

    loop.settings.research.enforce_strategy_eligibility = False
    loop.run_once()
    result = loop.run_once()

    outcomes = result["position_outcomes"]
    closed = [outcome for outcome in outcomes if outcome["status"] == "closed"]

    assert closed
    assert closed[0]["selected_exit_reason"] is not None


def test_new_entry_blocked_at_max_open_positions(
    decision_loop_environment,
    entry_snapshots,
    _seed_candles,
    test_store,
    monkeypatch,
):
    _seed_candles(test_store, 256265, "NIFTY", 60, "1m")
    _seed_candles(test_store, 256265, "NIFTY", 60, "15m")
    _seed_candles(test_store, 256265, "NIFTY", 60, "60m")

    provider = ReplayMarketDataProvider(entry_snapshots["snapshots"])
    loop = decision_loop_environment.build_loop(
        provider,
        proposal=entry_snapshots["proposal"],
    )

    loop.settings.research.enforce_feature_availability = False
    loop.settings.research.enforce_regime_policy = False
    loop.settings.research.enforce_strategy_eligibility = False
    # This test verifies position-capacity enforcement, not exits.
    # Prevent IV_COLLAPSE or any other exit from freeing capacity.
    monkeypatch.setattr(
        loop.exit_engine,
        "evaluate",
        lambda *args, **kwargs: SimpleNamespace(
            selected_reason=None,
        ),
    )
    monkeypatch.setattr(
        loop.positions,
        "save_exit_evaluation",
        lambda *_args, **_kwargs: None,
    )

    first = loop.run_once()
    print(
        "EXIT SETTINGS:",
        loop.exit_engine.exit_settings,
    )
    print("FIRST:", first["status"])
    print("FIRST EXIT:", first.get("exit_reason"))

    open_after_first = loop.positions.get_open_strategy_positions()
    print("OPEN AFTER FIRST:", len(open_after_first))

    assert first["status"] == "paper_filled"
    assert first.get("exit_reason") is None
    assert len(open_after_first) == 1
    print(
        "SECOND SNAPSHOT:",
        entry_snapshots["snapshots"][1].quotes[0].iv,
    )
    second = loop.run_once()
    print(
        "EXIT SETTINGS:",
        loop.exit_engine.exit_settings,
    )
    print("SECOND:", second["status"])
    print("SECOND OUTCOMES:", second["position_outcomes"])

    assert second["status"] == "max_open_positions"
    second_snapshot = entry_snapshots["snapshots"][1]
    assert any(quote.iv is not None for quote in second_snapshot.quotes)


def test_run_once_persists_chain_snapshot(
    decision_loop_environment,
    replay_snapshots,
):
    provider = ReplayMarketDataProvider(replay_snapshots["snapshots"])

    loop = decision_loop_environment.build_loop(
        provider,
        proposal=replay_snapshots["proposal"],
    )

    result = loop.run_once()

    rows = loop.store.conn.execute("SELECT COUNT(*) FROM option_stream").fetchone()[0]

    assert rows > 0
    assert result["persisted_option_rows"] > 0


def test_missing_regime_policy_blocks_new_entry(
    decision_loop_environment,
    replay_snapshots,
):
    provider = ReplayMarketDataProvider(replay_snapshots["snapshots"])

    loop = decision_loop_environment.build_loop(
        provider,
        proposal=replay_snapshots["proposal"],
    )

    loop.settings.research.enforce_regime_policy = True
    loop.settings.research.enforce_strategy_eligibility = False
    result = loop.run_once()

    assert result["status"] == "regime_policy_rejected"


def test_ready_policy_allows_matching_regime() -> None:
    policy = {
        "allowed_regimes": {"RANGE|HIGH"},
        "selection_status": "READY",
        "test_end": None,
    }

    current_regime = "RANGE|HIGH"
    allowed_regimes = policy["allowed_regimes"]
    assert isinstance(allowed_regimes, set)

    policy_allows = (
        policy is not None
        and policy["selection_status"] == "READY"
        and current_regime in allowed_regimes
    )

    assert policy_allows is True


def test_position_closes_on_iv_collapse(
    decision_loop_environment,
    entry_snapshots,
    _seed_candles,
    test_store,
):
    _seed_candles(test_store, 256265, "NIFTY", 60, "1m")
    _seed_candles(test_store, 256265, "NIFTY", 60, "15m")
    _seed_candles(test_store, 256265, "NIFTY", 60, "60m")

    provider = ReplayMarketDataProvider(entry_snapshots["snapshots"])
    loop = decision_loop_environment.build_loop(
        provider,
        proposal=entry_snapshots["proposal"],
    )
    loop.settings.research.enforce_strategy_eligibility = False
    loop.settings.research.enforce_feature_availability = False
    loop.settings.research.enforce_regime_policy = False

    loop.run_once()
    result = loop.run_once()

    outcomes = result["position_outcomes"]

    assert outcomes
    assert outcomes[0]["status"] == "closed"
    assert outcomes[0]["selected_exit_reason"] == "IV_COLLAPSE"
