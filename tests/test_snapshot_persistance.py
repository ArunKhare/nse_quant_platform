from nse_quant.market_data.replay_provider import ReplayMarketDataProvider


def test_run_once_persists_chain_snapshot(
    decision_loop_environment,
    replay_snapshots,
):
    provider = ReplayMarketDataProvider(replay_snapshots["snapshots"])

    loop = decision_loop_environment.build_loop(
        provider,
        proposal=replay_snapshots["proposal"],
    )
    loop.settings.research.enforce_strategy_eligibility = False
    loop.run_once()

    rows = loop.store.conn.execute("SELECT COUNT(*) FROM option_stream").fetchone()[0]

    assert rows > 0
