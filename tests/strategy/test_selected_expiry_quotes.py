from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from nse_quant.core.models import ChainSnapshot, Instrument, OptionQuote, OptionType
from nse_quant.core.settings import RiskSettings
from nse_quant.strategy.gates import LiquidityGate
from nse_quant.strategy.iron_condor import IronCondorMonitor

EXPIRY = date(2026, 2, 2)
OTHER = EXPIRY + timedelta(days=7)


def quote(expiry: date, strike: int, kind: OptionType, token: int,
          price: float = 50, oi: int = 100_000, underlying: str = "NIFTY") -> OptionQuote:
    instrument = Instrument(
        tradingsymbol=f"{underlying}-{expiry}-{strike}-{kind.value}",
        instrument_token=token, underlying=underlying, expiry=expiry,
        strike=strike, option_type=kind, lot_size=75,
    )
    return OptionQuote(
        instrument_token=token, instrument=instrument, ltp=price,
        bid=price * 0.995, ask=price * 1.005, oi=oi, volume=100_000,
    )


def snapshot(quotes: list[OptionQuote]) -> ChainSnapshot:
    return ChainSnapshot(underlying="NIFTY", spot=25_000, expiry=EXPIRY,
                         ts=datetime(2026, 1, 1, 6, tzinfo=UTC), quotes=quotes)


def own_quotes() -> list[OptionQuote]:
    return [quote(EXPIRY, strike, kind, index * 2 + offset + 1,
                  price=10 if abs(strike - 25_000) == 400 else 50)
            for index, strike in enumerate((24600, 24800, 25000, 25200, 25400))
            for offset, kind in enumerate((OptionType.CE, OptionType.PE))]


def strategy() -> IronCondorMonitor:
    monitor = IronCondorMonitor.__new__(IronCondorMonitor)
    monitor.config = SimpleNamespace(wing_distance_points=200, min_credit=20)
    monitor.risk_settings = RiskSettings()
    monitor.gates = Mock()
    monitor.gates.evaluate.return_value = []
    monitor.gates.all_passed.return_value = True
    return monitor


def features(expiry: date = EXPIRY, underlying: str = "NIFTY") -> SimpleNamespace:
    return SimpleNamespace(expiry=expiry, underlying=underlying, expected_move_points=500)


@pytest.mark.parametrize("foreign_first", [False, True])
def test_strategy_never_borrows_foreign_expiry_prices(foreign_first: bool) -> None:
    own = own_quotes()
    foreign = [quote(OTHER, int(q.instrument.strike), q.instrument.option_type,
                     100 + index, price=5000) for index, q in enumerate(own)]
    mixed = snapshot(foreign + own if foreign_first else own + foreign)
    monitor = strategy()
    proposal, _ = monitor.evaluate(mixed, features())
    assert proposal is not None
    assert all(leg.instrument.expiry == EXPIRY for leg in proposal.legs)
    assert sorted(leg.entry_price for leg in proposal.legs) == [10, 10, 50, 50]
    assert proposal.metadata["ignored_quote_count"] == len(foreign)
    passed_snapshot = monitor.gates.evaluate.call_args.args[0]
    assert all(q.instrument.expiry == EXPIRY for q in passed_snapshot.quotes)
    assert len(mixed.quotes) == len(own) + len(foreign)


def test_foreign_only_snapshot_cannot_propose() -> None:
    quotes = [q.model_copy(update={"instrument": q.instrument.model_copy(update={"expiry": OTHER})})
              for q in own_quotes()]
    monitor = strategy()
    proposal, gates = monitor.evaluate(snapshot(quotes), features())
    assert proposal is None
    assert gates[0].reason == "no_selected_expiry_quotes"
    monitor.gates.evaluate.assert_not_called()


def test_foreign_wings_cannot_fill_missing_selected_wings() -> None:
    own = [q for q in own_quotes() if abs(q.instrument.strike - 25_000) < 400]
    foreign = [quote(OTHER, strike, kind, 200 + index, price=10)
               for index, (strike, kind) in enumerate(((24600, OptionType.PE), (25400, OptionType.CE)))]
    proposal, gates = strategy().evaluate(snapshot(own + foreign), features())
    assert proposal is None
    assert any(g.reason == "no_liquid_long_wing" for g in gates)


@pytest.mark.parametrize("feature_values", [(OTHER, "NIFTY"), (EXPIRY, "BANKNIFTY")])
def test_mismatched_features_fail_closed(feature_values: tuple) -> None:
    monitor = strategy()
    proposal, gates = monitor.evaluate(snapshot(own_quotes()), features(*feature_values))
    assert proposal is None
    assert gates[0].reason == "feature_snapshot_mismatch"
    monitor.gates.evaluate.assert_not_called()


@pytest.mark.parametrize("foreign_first", [False, True])
def test_liquidity_cannot_be_rescued_by_foreign_oi(foreign_first: bool) -> None:
    own = [quote(EXPIRY, 25000, kind, index + 1, oi=0)
           for index, kind in enumerate((OptionType.CE, OptionType.PE))]
    foreign = [quote(OTHER, 25000, kind, index + 100)
               for index, kind in enumerate((OptionType.CE, OptionType.PE))]
    gate = LiquidityGate(settings=SimpleNamespace(risk=RiskSettings()))
    result = gate.evaluate(snapshot(foreign + own if foreign_first else own + foreign), [25000])
    assert not result.passed
    assert sum("low_oi" in failure for failure in result.details["failures"]) == 2


def test_liquidity_standalone_rejects_foreign_underlying() -> None:
    wrong = [quote(EXPIRY, 25000, kind, index + 1, underlying="BANKNIFTY")
             for index, kind in enumerate((OptionType.CE, OptionType.PE))]
    gate = LiquidityGate(settings=SimpleNamespace(risk=RiskSettings()))
    result = gate.evaluate(snapshot(wrong), [25000])
    assert not result.passed
    assert all("missing" in failure for failure in result.details["failures"])
