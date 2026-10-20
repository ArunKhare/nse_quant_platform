from datetime import UTC, date, datetime, timedelta

import pytest

from nse_quant.analytics.implied_volatility import implied_volatility
from nse_quant.analytics.iv_history import derive_atm_iv_observations
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

def test_atm_iv_observation_is_derived():
    rows = [
        (
            datetime(2026, 10, 18, 11, 30),
            23000.0,
            date(2026, 10, 19),
            23000.0,
            "CE",
            "NIFTY26O1923000CE",
            1,
            65,
            100.0,
            99.0,
            101.0,
            1000,
            2000,
            0.15,
            None,
            None,
            None,
            None,
        ),
        (
            datetime(2026, 10, 18, 11, 30),
            23000.0,
            date(2026, 10, 19),
            23000.0,
            "PE",
            "NIFTY26O1923000PE",
            2,
            65,
            100.0,
            99.0,
            101.0,
            1000,
            2000,
            0.17,
            None,
            None,
            None,
            None,
        ),
    ]

    observations = derive_atm_iv_observations(
        rows,
        underlying="NIFTY",
    )

    assert len(observations) == 1
    assert observations[0][2] == pytest.approx(0.16)


def test_iv_is_computed_for_atm_call():
    iv = implied_volatility(
        option_price=100.0,
        spot=23000.0,
        strike=23000.0,
        time_to_expiry_years=1 / 365,
        risk_free_rate=0.065,
        option_type="CE",
    )

    assert iv is not None
    assert 0.01 < iv < 5.0

