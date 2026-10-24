from datetime import UTC, date, datetime, timedelta

import pytest

from nse_quant.core.models import (
    ChainSnapshot,
    Instrument,
    MarketFeatures,
    OptionQuote,
    OptionType,
)
from nse_quant.strategy.iron_condor import IronCondorMonitor


@pytest.fixture
def snapshot(test_settings) -> ChainSnapshot:
    expiry = date.today() + timedelta(days=7)
    atm_strike = 25000.0
    wing = test_settings.get_strategy_profile("iron_condor_monitor").wing_distance_points
    strikes = [
        atm_strike - 2 * wing,
        atm_strike - wing,
        atm_strike,
        atm_strike + wing,
        atm_strike + 2 * wing,
    ]
    premiums = {
        (OptionType.PE, atm_strike - 2 * wing): 30.0,
        (OptionType.PE, atm_strike - wing): 80.0,
        (OptionType.CE, atm_strike + wing): 80.0,
        (OptionType.CE, atm_strike + 2 * wing): 30.0,
    }
    quotes = []
    token = 1

    for strike in strikes:
        for option_type in OptionType:
            instrument = Instrument(
                tradingsymbol=f"NIFTY{expiry:%y%b}{int(strike)}{option_type.value}",
                instrument_token=token,
                underlying="NIFTY",
                expiry=expiry,
                strike=strike,
                option_type=option_type,
                lot_size=65,
            )
            price = premiums.get((option_type, strike), 50.0)
            quotes.append(
                OptionQuote(
                    instrument_token=token,
                    instrument=instrument,
                    ltp=price,
                    bid=price - 0.05,
                    ask=price + 0.05,
                    volume=1000,
                    oi=100000,
                )
            )
            token += 1

    return ChainSnapshot(
        underlying="NIFTY",
        ts=datetime.now(UTC),
        spot=atm_strike,
        expiry=expiry,
        quotes=quotes,
    )


@pytest.fixture
def features(snapshot: ChainSnapshot) -> MarketFeatures:
    return MarketFeatures(
        ts=snapshot.ts,
        underlying=snapshot.underlying,
        spot=snapshot.spot,
        expiry=snapshot.expiry,
        iv_rank=70.0,
        iv_rv_spread=0.1,
        expected_move_points=300.0,
    )


@pytest.fixture
def iv_history() -> list[float]:
    return [0.14, 0.15, 0.16] * 10


def test_replay_and_live_produce_same_proposal(
    snapshot: ChainSnapshot,
    features: MarketFeatures,
    iv_history: list[float],
    test_settings,
):
    live_strategy = IronCondorMonitor(test_settings)
    replay_strategy = IronCondorMonitor(test_settings)

    live_proposal, live_gates = live_strategy.evaluate(
        snapshot=snapshot,
        features=features,
        iv_history_count=len(iv_history),
    )

    replay_proposal, replay_gates = replay_strategy.evaluate(
        snapshot=snapshot,
        features=features,
        iv_history_count=len(iv_history),
    )

    assert (live_proposal is None) == (replay_proposal is None)
    assert len(live_gates) == len(replay_gates)

    assert [gate.model_dump(mode="json") for gate in live_gates] == [
        gate.model_dump(mode="json") for gate in replay_gates
    ]

    assert live_proposal is not None
    assert replay_proposal is not None

    assert live_proposal.strategy == replay_proposal.strategy
    assert live_proposal.underlying == replay_proposal.underlying
    assert live_proposal.expiry == replay_proposal.expiry
    assert live_proposal.entry_limit_price == pytest.approx(replay_proposal.entry_limit_price)

    assert len(live_proposal.legs) == len(replay_proposal.legs)

    for live_leg, replay_leg in zip(
        live_proposal.legs,
        replay_proposal.legs,
        strict=True,
    ):
        assert live_leg.instrument.tradingsymbol == replay_leg.instrument.tradingsymbol
        assert live_leg.side == replay_leg.side
        assert live_leg.lots == replay_leg.lots
        assert live_leg.entry_price == pytest.approx(replay_leg.entry_price)
