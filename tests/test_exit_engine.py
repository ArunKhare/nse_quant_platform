from datetime import UTC, datetime, timedelta

from nse_quant.core.models import (
    ExitReason,
    Instrument,
    Leg,
    LegPosition,
    MarketFeatures,
    OptionType,
    OrderSide,
    StrategyPosition,
    TradeProposal,
)
from nse_quant.strategy.exit_engine import ExitEngine


def make_proposal():
    instrument = Instrument(
        tradingsymbol="NIFTY26OCT25000CE",
        instrument_token=1,
        underlying="NIFTY",
        expiry=datetime.now(UTC).date() + timedelta(days=5),
        strike=25000,
        option_type=OptionType.CE,
        lot_size=75,
    )

    leg = Leg(instrument=instrument, side=OrderSide.SELL, lots=1)

    return TradeProposal(
        strategy="iron_condor_monitor",
        underlying="NIFTY",
        expiry=instrument.expiry,
        thesis="Range-bound market",
        legs=[leg],
        entry_limit_price=100.0,
        target_price=50.0,
        stop_loss_price=180.0,
        expected_move_points=200.0,
    )


def test_stop_loss_has_priority_over_target():
    proposal = make_proposal()
    now = datetime.now(UTC)

    strategy_position = StrategyPosition(
        proposal_id=proposal.proposal_id,
        strategy=proposal.strategy,
        underlying=proposal.underlying,
        expiry=proposal.expiry,
        opened_at=now,
        entry_price=100.0,
        current_price=190.0,
    )

    leg_position = LegPosition(
        strategy_position_id=strategy_position.strategy_position_id,
        proposal_id=proposal.proposal_id,
        strategy=proposal.strategy,
        instrument=proposal.legs[0].instrument,
        side=OrderSide.SELL,
        lots=1,
        opened_at=now,
        entry_price=100.0,
        current_price=190.0,
    )

    features = MarketFeatures(
        ts=now,
        underlying="NIFTY",
        spot=25000,
        expiry=proposal.expiry,
        atm_iv=15,
        iv_rank=50,
        expected_move_points=100,
    )

    evaluation = ExitEngine().evaluate(
        proposal,
        strategy_position,
        [leg_position],
        features,
        kill_switch_active=True,
        risk_breached=True,
    )

    assert ExitReason.MANUAL_KILL_SWITCH in evaluation.triggered_reasons
    assert ExitReason.RISK_LIMIT_BREACH in evaluation.triggered_reasons
    assert ExitReason.STOP_LOSS in evaluation.triggered_reasons
    assert evaluation.selected_reason == ExitReason.MANUAL_KILL_SWITCH


def test_no_exit_when_no_rules_trigger():
    proposal = make_proposal()
    now = datetime.now(UTC)

    strategy_position = StrategyPosition(
        proposal_id=proposal.proposal_id,
        strategy=proposal.strategy,
        underlying=proposal.underlying,
        expiry=proposal.expiry,
        opened_at=now,
        entry_price=100.0,
        current_price=90.0,
    )

    features = MarketFeatures(
        ts=now,
        underlying="NIFTY",
        spot=25000,
        expiry=proposal.expiry + timedelta(days=1),
        atm_iv=15,
        iv_rank=70,
        expected_move_points=100,
    )

    evaluation = ExitEngine().evaluate(
        proposal,
        strategy_position,
        [],
        features,
    )

    assert evaluation.triggered_reasons == []
    assert evaluation.selected_reason is None