from datetime import UTC, date, datetime, timedelta

from nse_quant.core.models import (
    Instrument,
    Leg,
    MarketFeatures,
    OptionType,
    OrderSide,
    StrategyPosition,
    StrategyPositionStatus,
    TradeProposal,
)
from nse_quant.strategy.exit_engine import ExitEngine


def _expiry():
    return datetime.now(UTC).date() + timedelta(days=1)


def _instrument(
    token: int,
    strike: float,
    option_type: OptionType,
    expiry: date,
) -> Instrument:
    return Instrument(
        tradingsymbol=f"NIFTY{strike}{option_type.value}",
        instrument_token=token,
        underlying="NIFTY",
        expiry=expiry,
        strike=strike,
        option_type=option_type,
        lot_size=75,
    )


def _proposal() -> TradeProposal:
    expiry = _expiry()
    long_put = _instrument(1, 24000, OptionType.PE, expiry)
    short_put = _instrument(2, 24100, OptionType.PE, expiry)
    short_call = _instrument(3, 24200, OptionType.CE, expiry)
    long_call = _instrument(4, 24300, OptionType.CE, expiry)

    legs = [
        Leg(
            instrument=long_put,
            side=OrderSide.BUY,
            lots=1,
            entry_price=80.0,
        ),
        Leg(
            instrument=short_put,
            side=OrderSide.SELL,
            lots=1,
            entry_price=120.0,
        ),
        Leg(
            instrument=short_call,
            side=OrderSide.SELL,
            lots=1,
            entry_price=110.0,
        ),
        Leg(
            instrument=long_call,
            side=OrderSide.BUY,
            lots=1,
            entry_price=70.0,
        ),
    ]

    net_credit = (120.0 + 110.0 - 80.0 - 70.0) * 75

    return TradeProposal(
        strategy="iron_condor_monitor",
        underlying="NIFTY",
        expiry=expiry,
        thesis="Test iron condor",
        legs=legs,
        entry_limit_price=net_credit,
        target_price=net_credit * 0.5,
        stop_loss_price=net_credit * 2.0,
    )


def _strategy_position(proposal: TradeProposal) -> StrategyPosition:
    return StrategyPosition(
        proposal_id=proposal.proposal_id,
        strategy=proposal.strategy,
        underlying=proposal.underlying,
        expiry=proposal.expiry,
        opened_at=datetime.now(UTC),
        entry_price=proposal.entry_limit_price,
        current_price=proposal.entry_limit_price,
        status=StrategyPositionStatus.OPEN,
    )


def _features(expiry: date) -> MarketFeatures:
    return MarketFeatures(
        ts=datetime.now(UTC),
        underlying="NIFTY",
        spot=22550.0,
        expiry=expiry,
    )


def test_target_profit_does_not_trigger_at_entry():
    proposal = _proposal()
    position = _strategy_position(proposal)

    evaluation = ExitEngine().evaluate(
        proposal=proposal,
        strategy_position=position,
        leg_positions=[],
        features=_features(proposal.expiry),
    )

    assert position.current_price == proposal.entry_limit_price
    assert position.current_price > proposal.target_price
    assert evaluation.selected_reason is None
    assert "TARGET_PROFIT" not in evaluation.triggered_reasons


def test_target_profit_triggers_at_remaining_credit_target():
    proposal = _proposal()
    position = _strategy_position(proposal)

    position.current_price = proposal.target_price

    evaluation = ExitEngine().evaluate(
        proposal=proposal,
        strategy_position=position,
        leg_positions=[],
        features=_features(proposal.expiry),
    )

    assert "TARGET_PROFIT" in evaluation.triggered_reasons
    assert evaluation.selected_reason == "TARGET_PROFIT"


def test_target_profit_does_not_trigger_above_target():
    proposal = _proposal()
    position = _strategy_position(proposal)

    assert proposal.target_price is not None
    position.current_price = proposal.target_price + 1.0

    evaluation = ExitEngine().evaluate(
        proposal=proposal,
        strategy_position=position,
        leg_positions=[],
        features=_features(proposal.expiry),
    )

    assert "TARGET_PROFIT" not in evaluation.triggered_reasons
