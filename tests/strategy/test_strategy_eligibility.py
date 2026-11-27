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
from nse_quant.core.regime_registry import is_canonical_regime_label
from nse_quant.core.settings import Settings
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
        regime_label="UNKNOWN",
        regime_allowed=False,
        regime_policy=None,
        regime_source="test",
    )

    assert gate.passed is False
    assert gate.reason == "IV regime not allowed: UNKNOWN"
    assert gate.details["regime_label"] == "UNKNOWN"
    assert gate.details["intraday_shape"] == "UNKNOWN"
    assert gate.details["market_context"]["daily_trend_vol"] is None
    assert "current_regime" not in gate.details


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
        regime_label=allowed_regime,
        regime_allowed=True,
        regime_policy=None,
        regime_source="test",
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


def test_liquidity_gate_uses_effective_strategy_risk():
    settings = Settings.model_validate(
        {
            "risk": {"max_spread_pct": 0.03},
            "strategies": {
                "iron_condor_monitor": {
                    "enabled": True,
                    "strategy_type": "iron_condor",
                    "underlyings": ["NIFTY"],
                    "wing_distance_points": 200,
                    "min_credit": 20,
                    "risk": {"max_spread_pct": 0.05},
                }
            },
        }
    )

    strategy = IronCondorMonitor(settings)

    assert strategy.gates.liquidity_gate.risk_limits.max_spread_pct == 0.05


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


def test_regime_risk_uses_static_configured_limits_until_canonical_policy_ready(
    decision_loop_environment,
):
    loop = decision_loop_environment.build_loop(
        SimpleNamespace(),
        enforce_strategy_eligibility=True,
    )
    configured_regimes = loop.settings.get_strategy_profile("iron_condor_monitor").regime_policy.allowed_regimes
    regime = next(label for label in configured_regimes if is_canonical_regime_label(label))
    configured = loop.settings.get_effective_risk_settings("iron_condor_monitor")

    limits = loop._apply_regime_limits(current_regime=regime, regime_policy=None)

    assert limits.allowed is True
    assert limits.reason == "STATIC_CONFIGURED_FALLBACK"
    assert limits.max_lots_per_order == configured.max_lots_per_order
    assert limits.max_open_positions == configured.max_open_positions
    assert limits.max_notional_exposure == configured.max_notional_exposure


def test_regime_risk_static_fallback_still_fails_closed_for_noncanonical_label(
    decision_loop_environment,
):
    loop = decision_loop_environment.build_loop(
        SimpleNamespace(),
        enforce_strategy_eligibility=True,
    )

    limits = loop._apply_regime_limits(current_regime="RANGE|HIGH", regime_policy=None)

    assert limits.allowed is False
    assert limits.reason == "non_canonical_regime"
    assert limits.max_lots_per_order == 0
