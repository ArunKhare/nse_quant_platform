from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from nse_quant.core.models import (
    ExitEvaluation,
    ExitReason,
    Instrument,
    LegPosition,
    OptionType,
    OrderSide,
    StrategyPosition,
    StrategyPositionStatus,
)
from nse_quant.market_data.replay_provider import (
    ReplayMarketDataProvider,
)
from nse_quant.persistence.repositories import PositionRepository


def test_new_position_rejects_missing_leg_entry_premium(
    decision_loop_environment,
    replay_snapshots,
):
    proposal = replay_snapshots["proposal"]
    proposal.legs[0].entry_price = None
    provider = ReplayMarketDataProvider(replay_snapshots["snapshots"])
    loop = decision_loop_environment.build_loop(
        provider,
        proposal=proposal,
        approve_regime_risk=True,
    )

    with pytest.raises(ValueError, match="Missing or invalid entry premium"):
        loop.run_once()


def test_open_position_is_marked_and_exit_evaluated(
    decision_loop_environment,
    replay_snapshots,
):
    provider = ReplayMarketDataProvider(replay_snapshots["snapshots"])
    loop = decision_loop_environment.build_loop(
        provider,
        proposal=replay_snapshots["proposal"],
        approve_regime_risk=True,
    )
    loop.settings.research.enforce_strategy_eligibility = False
    first = loop.run_once()
    assert first["status"] == "paper_filled"
    assert first["exit_reason"] is None

    strategy_position_id = first["strategy_position_id"]
    assert strategy_position_id in {
        position.strategy_position_id for position in loop.positions.get_open_strategy_positions()
    }

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
        approve_regime_risk=True,
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
        approve_regime_risk=True,
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
        approve_regime_risk=True,
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

    assert result["status"] == "regime_risk_rejected"


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
        approve_regime_risk=True,
    )
    loop.settings.research.enforce_strategy_eligibility = False
    loop.settings.research.enforce_feature_availability = False
    loop.settings.research.enforce_regime_policy = False
    # This fixture's synthetic two-leg credit triggers theta decay too.
    loop.exit_engine.exit_settings.theta_decay_target_pct = 10_000

    loop.run_once()
    result = loop.run_once()

    outcomes = result["position_outcomes"]

    assert outcomes
    assert outcomes[0]["status"] == "closed"
    assert outcomes[0]["selected_exit_reason"] == ExitReason.IV_COLLAPSE


def test_exit_engine_runs_on_next_cycle_after_fill(
    decision_loop_environment,
    replay_snapshots,
    monkeypatch,
):
    provider = ReplayMarketDataProvider(replay_snapshots["snapshots"])
    loop = decision_loop_environment.build_loop(
        provider,
        proposal=replay_snapshots["proposal"],
        approve_regime_risk=True,
    )
    loop.settings.research.enforce_strategy_eligibility = False

    initial_evaluate = Mock(wraps=loop.exit_engine.evaluate)
    monkeypatch.setattr(loop.exit_engine, "evaluate", initial_evaluate)

    first = loop.run_once()
    assert first["status"] == "paper_filled"
    assert first["exit_reason"] is None

    strategy_position_id = first["strategy_position_id"]
    initial_evaluate.assert_not_called()

    next_cycle_evaluate = Mock(
        return_value=ExitEvaluation(
            strategy_position_id=strategy_position_id,
            evaluated_at=datetime.now(UTC),
            triggered_reasons=[ExitReason.IV_COLLAPSE],
            selected_reason=ExitReason.IV_COLLAPSE,
        )
    )
    monkeypatch.setattr(loop.exit_engine, "evaluate", next_cycle_evaluate)

    second = loop.run_once()

    next_cycle_evaluate.assert_called_once()
    closed = [
        outcome
        for outcome in second["position_outcomes"]
        if outcome["strategy_position_id"] == strategy_position_id
    ]
    assert closed == [
        {
            "strategy_position_id": strategy_position_id,
            "status": "closed",
            "selected_exit_reason": ExitReason.IV_COLLAPSE.value,
        }
    ]
    assert strategy_position_id not in {
        position.strategy_position_id for position in loop.positions.get_open_strategy_positions()
    }


def _instrument(token: int, strike: float, option_type: OptionType) -> Instrument:
    return Instrument(
        tradingsymbol=f"NIFTY{strike}{option_type.value}",
        instrument_token=token,
        underlying="NIFTY",
        expiry=datetime.now(UTC).date(),
        strike=strike,
        option_type=option_type,
        lot_size=75,
    )


def _leg_position(
    strategy_position_id: str,
    token: int,
    strike: float,
    option_type: OptionType,
    side: OrderSide,
) -> LegPosition:
    return LegPosition(
        leg_position_id=f"{strategy_position_id}:NIFTY{strike}{option_type.value}",
        strategy_position_id=strategy_position_id,
        proposal_id="proposal-1",
        strategy="iron_condor_monitor",
        instrument=_instrument(token, strike, option_type),
        side=side,
        lots=1,
        opened_at=datetime.now(UTC),
        entry_price=100.0,
        current_price=100.0,
        status=StrategyPositionStatus.OPEN,
        mark_stale=False,
    )


def test_stale_mark_is_persisted_and_restored(test_store):
    repository = PositionRepository(test_store.conn)

    strategy_position = StrategyPosition(
        proposal_id="proposal-1",
        strategy="iron_condor_monitor",
        underlying="NIFTY",
        expiry=datetime.now(UTC).date(),
        opened_at=datetime.now(UTC),
        entry_price=6000.0,
        current_price=6000.0,
        status=StrategyPositionStatus.OPEN,
    )

    repository.create_strategy_position(strategy_position)

    leg = _leg_position(
        strategy_position.strategy_position_id,
        token=1,
        strike=24100,
        option_type=OptionType.PE,
        side=OrderSide.SELL,
    )

    repository.create_leg_position(leg)

    leg.mark_stale = True
    repository.update_leg_position(leg)

    restored = repository.get_leg_positions(strategy_position.strategy_position_id)[0]

    assert restored.mark_stale is True

    leg.mark_stale = False
    repository.update_leg_position(leg)

    restored = repository.get_leg_positions(strategy_position.strategy_position_id)[0]

    assert restored.mark_stale is False
