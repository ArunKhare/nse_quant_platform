"""Synthetic S2 kernel tests; not acquisition provenance or native replay E2E."""

import math
from datetime import UTC, datetime, timedelta

import pytest

from nse_quant.analytics.constant_maturity_inputs import (
    ForwardPoint,
    PremiumPoint,
    SurfaceInputError,
    black76_price,
    build_surface_inputs,
    constant_maturity,
)

AS_OF = datetime(2026, 11, 24, 6, 0, tzinfo=UTC)


def surface_case():
    quotes, forwards = [], []
    token = 0
    for days in (20, 40, 80, 100):
        expiry = AS_OF + timedelta(days=days)
        forwards.append(
            ForwardPoint(
                "NIFTY",
                expiry,
                100.0,
                0.05,
                AS_OF,
                AS_OF,
                "synthetic_test_fixture",
                f"fixture-forward-{days}",
            )
        )
        for kind in ("CE", "PE"):
            sigma = 0.20 if kind == "CE" else 0.24
            for strike in (85.0, 95.0, 100.0, 105.0, 115.0):
                token += 1
                premium = black76_price(100.0, strike, days / 365, 0.05, sigma, kind)
                quotes.append(
                    PremiumPoint(
                        token,
                        "NIFTY",
                        "synthetic-s2-batch",
                        expiry,
                        strike,
                        kind,
                        premium * 0.999,
                        premium * 1.001,
                        AS_OF,
                        AS_OF,
                    )
                )
    return quotes, forwards


def test_total_variance_interpolation_not_linear_iv():
    points = [(AS_OF + timedelta(days=20), 0.2), (AS_OF + timedelta(days=40), 0.3)]
    result = constant_maturity(points, as_of=AS_OF, days=30)
    expected = math.sqrt((0.5 * 0.2**2 * 20 + 0.5 * 0.3**2 * 40) / 30)
    assert result.iv == pytest.approx(expected)
    assert result.iv != pytest.approx(0.25)
    assert result.upper_weight == pytest.approx(0.5)


def test_no_maturity_extrapolation():
    with pytest.raises(SurfaceInputError, match="no_extrapolation"):
        constant_maturity([(AS_OF + timedelta(days=20), 0.2), (AS_OF + timedelta(days=40), 0.3)], as_of=AS_OF, days=90)


def test_sub_seven_day_expiry_does_not_supply_bracket():
    with pytest.raises(SurfaceInputError, match="no_extrapolation"):
        constant_maturity([(AS_OF + timedelta(days=6), 0.2), (AS_OF + timedelta(days=40), 0.3)], as_of=AS_OF, days=30)


def test_surface_rr25_sign_and_observation_only():
    quotes, forwards = surface_case()
    result = build_surface_inputs(quotes, forwards, as_of=AS_OF)
    assert result.call25_30.iv == pytest.approx(0.20, abs=1e-8)
    assert result.put25_30.iv == pytest.approx(0.24, abs=1e-8)
    assert result.rr25 == pytest.approx(-0.04, abs=1e-8)
    assert result.rr25 == result.call25_30.iv - result.put25_30.iv
    assert result.iv30.days == 30 and result.iv90.days == 90
    assert result.mode == "observation"
    assert result.decision_eligibility_asserted is False
    assert result.iv_source == "internal_cm"
    assert len(result.forward_reference_ids) == 4
    assert set(result.used_tokens) == {quote.token for quote in quotes}


def test_missing_forward_not_replaced_by_spot():
    quotes, forwards = surface_case()
    with pytest.raises(SurfaceInputError, match="matching_expiry_forward_missing"):
        build_surface_inputs(quotes, forwards[:-1], as_of=AS_OF)


def test_missing_wing_not_replaced_by_nearest_quote():
    quotes, forwards = surface_case()
    quotes = [quote for quote in quotes if quote.option_type != "CE" or quote.strike <= 100]
    with pytest.raises(SurfaceInputError, match="no_extrapolation"):
        build_surface_inputs(quotes, forwards, as_of=AS_OF)


def test_stale_inputs_rejected():
    quotes, forwards = surface_case()
    with pytest.raises(SurfaceInputError, match="stale"):
        build_surface_inputs(quotes, forwards, as_of=AS_OF + timedelta(seconds=301))
