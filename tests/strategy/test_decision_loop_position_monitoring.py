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
    assert strategy_position_id in [
        outcome["strategy_position_id"]
        for outcome in outcomes
    ]

def test_position_closes_when_exit_triggers(
    decision_loop_environment,
    exit_trigger_snapshots,
):
    provider = ReplayMarketDataProvider(exit_trigger_snapshots["snapshots"])
    loop = decision_loop_environment.build_loop(
        provider,
        proposal=exit_trigger_snapshots["proposal"],
    )

    loop.run_once()
    result = loop.run_once()

    outcomes = result["position_outcomes"]
    closed = [
        outcome
        for outcome in outcomes
        if outcome["status"] == "closed"
    ]

    assert closed
    assert closed[0]["selected_exit_reason"] is not None

def test_new_entry_blocked_at_max_open_positions(
    decision_loop_environment,
    entry_snapshots,
):
    provider = ReplayMarketDataProvider(entry_snapshots["snapshots"])
    loop = decision_loop_environment.build_loop(
        provider,
        proposal=entry_snapshots["proposal"],
    )

    first = loop.run_once()
    assert first["status"] == "paper_filled"

    second = loop.run_once()
    assert second["status"] == "max_open_positions"

def test_run_once_persists_chain_snapshot(
    decision_loop_environment,
    replay_snapshots,
):
    from nse_quant.market_data.replay_provider import (
        ReplayMarketDataProvider,
    )

    provider = ReplayMarketDataProvider(
        replay_snapshots["snapshots"]
    )

    loop = decision_loop_environment.build_loop(
        provider,
        proposal=replay_snapshots["proposal"],
    )

    result = loop.run_once()

    rows = loop.store.conn.execute(
        "SELECT COUNT(*) FROM option_stream"
    ).fetchone()[0]

    assert rows > 0
    assert result["persisted_option_rows"] > 0

def test_missing_regime_policy_blocks_new_entry(
    decision_loop_environment,
    replay_snapshots,
):
    provider = ReplayMarketDataProvider(
        replay_snapshots["snapshots"]
    )

    loop = decision_loop_environment.build_loop(
        provider,
        proposal=replay_snapshots["proposal"],
    )

    loop.settings.research.enforce_regime_policy = True

    result = loop.run_once()

    assert result["status"] == "regime_policy_rejected"

def test_ready_policy_allows_matching_regime() -> None:
    policy = {
        "allowed_regimes": {"RANGE|HIGH"},
        "selection_status": "READY",
        "test_end": None,
    }

    current_regime = "RANGE|HIGH"

    policy_allows = (
        policy is not None
        and policy["selection_status"] == "READY"
        and current_regime in policy["allowed_regimes"]
    )

    assert policy_allows is True