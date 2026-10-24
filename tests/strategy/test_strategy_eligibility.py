from types import SimpleNamespace

from nse_quant.core.models import (
    ChainSnapshot,
    GateResult,
    MarketFeatures,
    OptionQuote,
    OptionType,
    OrderSide,
    OrderStatus,
)
from nse_quant.execution.broker import PaperBroker
from nse_quant.strategy.iron_condor import IronCondorMonitor


def make_features(iv_rank=None):
    return MarketFeatures(
        ts=__import__("datetime").datetime.now(__import__("datetime").UTC),
        underlying="NIFTY",
        spot=25000,
        expiry=__import__("datetime").date.today(),
        iv_rank=iv_rank,
    )


def build_valid_iron_condor_proposal(
    expiry,
    instrument_factory,
    test_settings,
    monkeypatch,
):
    monitor = IronCondorMonitor(settings=test_settings)
    atm_strike = 25000
    wing = monitor.config.wing_distance_points
    quote_details = [
        (atm_strike, OptionType.CE, 0, 100.0),
        (atm_strike - 2 * wing, OptionType.PE, 1, 5.0),
        (atm_strike - wing, OptionType.PE, 2, 15.0),
        (atm_strike + wing, OptionType.CE, 3, 15.0),
        (atm_strike + 2 * wing, OptionType.CE, 4, 5.0),
    ]

    snapshot = ChainSnapshot(
        underlying="NIFTY",
        spot=atm_strike,
        expiry=expiry,
        quotes=[
            OptionQuote(
                instrument_token=token,
                instrument=instrument_factory(strike, option_type, token),
                ltp=price,
            )
            for strike, option_type, token, price in quote_details
        ],
    )
    monkeypatch.setattr(
        monitor.gates,
        "evaluate",
        lambda *_args, **_kwargs: [GateResult(gate="test", passed=True, reason="Test gate passed")],
    )
    proposal, _ = monitor.evaluate(snapshot, make_features())

    assert proposal is not None
    return proposal


def test_eligibility_rejects_unknown_regime(decision_loop_environment):
    loop = decision_loop_environment.build_loop(
        SimpleNamespace(),
        enforce_strategy_eligibility=True,
    )

    profile = loop.settings.get_strategy_profile("iron_condor_monitor")

    gate = loop._evaluate_strategy_eligibility(
        profile=profile,
        features=make_features(iv_rank=50),
        iv_history_count=50,
        current_regime="UNKNOWN",
        regime_allowed=False,
        regime_policy=None,
    )

    assert gate.passed is False
    assert gate.reason == "IV regime not allowed: UNKNOWN"


def test_eligibility_rejects_missing_iv_rank(
    decision_loop_environment,
):
    loop = decision_loop_environment.build_loop(
        SimpleNamespace(),
        enforce_strategy_eligibility=True,
    )

    profile = loop.settings.get_strategy_profile("iron_condor_monitor")

    allowed_regime = profile.regime_policy.allowed_regimes[0]

    gate = loop._evaluate_strategy_eligibility(
        profile=profile,
        features=make_features(iv_rank=None),
        iv_history_count=50,
        current_regime=allowed_regime,
        regime_allowed=True,
        regime_policy=None,
    )

    assert gate.passed is False
    assert gate.reason == "IV rank unavailable"


def test_iron_condor_entry_credit_matches_distinct_leg_prices(
    expiry,
    instrument_factory,
    test_settings,
    monkeypatch,
):
    proposal = build_valid_iron_condor_proposal(
        expiry,
        instrument_factory,
        test_settings,
        monkeypatch,
    )

    premiums = [leg.entry_price for leg in proposal.legs]

    def signed_entry_value(leg):
        assert leg.entry_price is not None
        return leg.entry_price * leg.quantity * (1 if leg.side == OrderSide.SELL else -1)

    net_credit = sum(signed_entry_value(leg) for leg in proposal.legs)

    assert len(set(premiums)) > 1
    assert proposal.entry_limit_price > 0
    assert proposal.entry_limit_price == net_credit


def test_paper_broker_marks_remaining_credit(
    expiry,
    instrument_factory,
    test_settings,
    monkeypatch,
):
    broker = PaperBroker()
    proposal = build_valid_iron_condor_proposal(
        expiry,
        instrument_factory,
        test_settings,
        monkeypatch,
    )

    order = broker.submit(proposal)
    position = broker.positions()[0]

    assert order.status == OrderStatus.FILLED
    assert position.entry_price == proposal.entry_limit_price
    assert position.current_price == proposal.entry_limit_price
    assert position.unrealized_pnl == 0.0
    assert position.leg_entry_prices == {
        leg.instrument.instrument_token: leg.entry_price for leg in proposal.legs
    }

    entry_prices: dict[int, float] = {}
    for leg in proposal.legs:
        assert leg.entry_price is not None
        entry_prices[leg.instrument.instrument_token] = leg.entry_price
    marked = broker.mark_position(position.position_id, entry_prices)

    assert marked is position
    assert position.current_price == proposal.entry_limit_price
    assert position.unrealized_pnl == 0.0

    current_prices = {1: 6.0, 2: 14.0, 3: 13.0, 4: 7.0}
    marked = broker.mark_position(position.position_id, current_prices)
    remaining_credit = sum(
        current_prices[leg.instrument.instrument_token]
        * leg.quantity
        * (1 if leg.side == OrderSide.SELL else -1)
        for leg in proposal.legs
    )

    assert marked is position
    assert position.current_price == remaining_credit
    assert position.unrealized_pnl == proposal.entry_limit_price - remaining_credit
