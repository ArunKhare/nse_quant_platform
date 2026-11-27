"""Tests for canonical calculation primitives."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from nse_quant.core.calculations import (
    atm_iv,
    black_scholes_price_and_greeks,
    classify_intraday_shape,
    implied_volatility,
    iv_percentile,
    iv_rank,
    realized_volatility,
    time_to_expiry_years,
)


def test_time_to_expiry_uses_365_25_day_basis():
    as_of = datetime(2026, 1, 1, tzinfo=UTC)
    expiry = datetime(2027, 1, 1, tzinfo=UTC)
    expected = 365 / 365.25
    assert time_to_expiry_years(as_of=as_of, expiry=expiry) == pytest.approx(expected, rel=1e-12)


def test_black_scholes_call_put_parity():
    call = black_scholes_price_and_greeks(
        spot=100,
        strike=100,
        time_to_expiry_years=0.5,
        risk_free_rate=0.07,
        implied_volatility=0.25,
        option_type="CE",
    )[0]
    put = black_scholes_price_and_greeks(
        spot=100,
        strike=100,
        time_to_expiry_years=0.5,
        risk_free_rate=0.07,
        implied_volatility=0.25,
        option_type="PE",
    )[0]
    expected = 100 - 100 * pow(2.718281828459045, -0.07 * 0.5)
    assert call - put == pytest.approx(expected, rel=1e-10)


def test_implied_volatility_recovers_known_iv():
    price, *_ = black_scholes_price_and_greeks(
        spot=100,
        strike=100,
        time_to_expiry_years=0.5,
        risk_free_rate=0.07,
        implied_volatility=0.25,
        option_type="CE",
    )

    iv = implied_volatility(
        option_price=price,
        spot=100,
        strike=100,
        time_to_expiry_years=0.5,
        risk_free_rate=0.07,
        option_type="CE",
    )

    assert iv == pytest.approx(0.25, rel=1e-8)


def test_realized_volatility_requires_complete_window():
    assert realized_volatility([100, 101, 102], window=20) is None


def test_iv_rank_bounds_and_flat_history():
    assert iv_rank(20, [10, 20, 30]) == 50
    assert iv_rank(20, [20, 20]) == 50
    assert iv_rank(None, [10, 20]) is None


def test_iv_percentile_bounds():
    assert iv_percentile(20, [10, 20, 30]) == pytest.approx(100 / 3)
    assert iv_percentile(None, [10, 20]) is None


def test_atm_iv_selects_nearest_positive_finite_iv():
    result = atm_iv({90: 0.2, 100: 0.3, 110: 0.4}, spot=101)
    assert result == 0.3


def test_intraday_shape_classification():
    assert classify_intraday_shape(spot=100, fast_sma=101, slow_sma=100, realized_volatility=0.2).value == "TREND_UP"
    assert classify_intraday_shape(spot=100, fast_sma=99, slow_sma=100, realized_volatility=0.2).value == "TREND_DOWN"
    assert classify_market_regime(spot=100, fast_sma=100, slow_sma=100, realized_volatility=0.4).value == "VOLATILE"
