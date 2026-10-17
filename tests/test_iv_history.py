from datetime import UTC, datetime, timedelta

from nse_quant.core.models import MarketFeatures
from nse_quant.strategy.gates import IvRegimeGate


def make_features(iv_rank: float | None) -> MarketFeatures:
    return MarketFeatures(
        ts=datetime.now(UTC),
        underlying="NIFTY",
        spot=25000.0,
        expiry=datetime.now(UTC).date() + timedelta(days=5),
        atm_iv=15.0,
        iv_rank=iv_rank,
        iv_rv_spread=0.10,
    )


def test_cold_start_allows_missing_iv_rank():
    gate = IvRegimeGate()

    result = gate.evaluate(
        make_features(iv_rank=None),
        iv_history_count=0,
    )

    assert result.passed
    assert result.details["mode"] == "COLD_START"


def test_enforced_mode_requires_minimum_history():
    gate = IvRegimeGate()

    result = gate.evaluate(
        make_features(iv_rank=20.0),
        iv_history_count=30,
    )

    assert not result.passed
    assert result.details["mode"] == "ENFORCED"


def test_enforced_mode_passes_sufficient_rank():
    gate = IvRegimeGate()

    result = gate.evaluate(
        make_features(iv_rank=55.0),
        iv_history_count=30,
    )

    assert result.passed
    assert result.details["mode"] == "ENFORCED"