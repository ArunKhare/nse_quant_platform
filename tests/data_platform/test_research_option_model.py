"""Actual SciPy model/solver tests, not native market-data or decision E2E."""

import math
from dataclasses import replace

import pytest

from nse_quant.data_platform.research_option_model import (
    ScenarioTerms,
    compute_research_iv,
    decimal_input,
    price_and_greeks,
    scenario_terms_sha256,
)


def terms(kind="CE", **changes):
    value = dict(
        strike="100",
        annual_rate="0.05",
        annual_dividend_yield="0.02",
        assumed_years_to_expiry="1",
        option_type=kind,
    )
    value.update(changes)
    return ScenarioTerms(**value)


def test_known_european_continuous_dividend_values():
    call = price_and_greeks(100, 100, 1, 0.05, 0.02, 0.2, "CE")
    put = price_and_greeks(100, 100, 1, 0.05, 0.02, 0.2, "PE")
    assert call.price == pytest.approx(9.227005508154, abs=1e-10)
    assert put.price == pytest.approx(6.33008062755, abs=1e-10)
    assert call.price - put.price == pytest.approx(100 * math.exp(-0.02) - 100 * math.exp(-0.05))
    assert call.delta - put.delta == pytest.approx(math.exp(-0.02))
    assert call.gamma == put.gamma
    assert call.vega_per_vol_unit == put.vega_per_vol_unit


@pytest.mark.parametrize("kind", ["CE", "PE"])
@pytest.mark.parametrize("sigma", [0.05, 0.2, 0.8, 2.0])
def test_solver_recovers_volatility_from_actual_model(kind, sigma):
    expected = price_and_greeks(100, 100, 1, 0.05, 0.02, sigma, kind)
    premium = f"{expected.price:.12f}"
    value = compute_research_iv(spot_decimal="100", premium_decimal=premium, terms=terms(kind))
    assert value.status == "computed_research_scenario"
    assert value.implied_volatility == pytest.approx(sigma, abs=1e-9)
    assert abs(value.price_residual) <= 1e-8 + 1e-10 * max(float(premium), 1)
    assert not value.model_suitability_verified
    assert not value.underlying_identity_verified
    assert not value.historical_validity_asserted
    assert not value.publication_asserted
    assert not value.decision_eligibility_asserted
    assert value.canonical_contract_id is None


@pytest.mark.parametrize("kind", ["CE", "PE"])
def test_greeks_match_independent_central_differences(kind):
    spot, strike, years, rate, dividend, sigma = 105.0, 100.0, 0.75, 0.04, 0.015, 0.3
    actual = price_and_greeks(spot, strike, years, rate, dividend, sigma, kind)
    h = 0.001

    def price(s=spot, t=years, r=rate, v=sigma):
        return price_and_greeks(s, strike, t, r, dividend, v, kind).price

    assert actual.delta == pytest.approx(
        (price(s=spot + h) - price(s=spot - h)) / (2 * h), rel=1e-7
    )
    assert actual.gamma == pytest.approx(
        (price(s=spot + h) - 2 * price() + price(s=spot - h)) / h**2, rel=1e-4
    )
    step = 1e-5
    assert actual.vega_per_vol_unit == pytest.approx(
        (price(v=sigma + step) - price(v=sigma - step)) / (2 * step), rel=1e-7
    )
    assert actual.rho_per_rate_unit == pytest.approx(
        (price(r=rate + step) - price(r=rate - step)) / (2 * step), rel=1e-7
    )
    assert actual.theta_per_calendar_day == pytest.approx(
        -(price(t=years + step) - price(t=years - step)) / (2 * step * 365), rel=1e-7
    )


@pytest.mark.parametrize("kind,premium", [("CE", "100"), ("CE", "1"), ("PE", "100")])
def test_strict_no_arbitrage_bounds(kind, premium):
    value = compute_research_iv(spot_decimal="100", premium_decimal=premium, terms=terms(kind))
    assert value.status == "review_required"
    assert value.implied_volatility is None


def test_supported_bracket_is_not_silently_expanded():
    value = compute_research_iv(spot_decimal="100", premium_decimal="98", terms=terms())
    assert value.status == "review_required"
    assert value.reason_codes == ("IV_OUTSIDE_SUPPORTED_VOLATILITY_BRACKET",)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "1e2", " 100", "01", True, 100.0])
def test_exact_plain_decimal_inputs(value):
    with pytest.raises(ValueError):
        decimal_input(value)


@pytest.mark.parametrize(
    "changes",
    [
        {"strike": "0"},
        {"annual_rate": "1.1"},
        {"annual_dividend_yield": "-0.3"},
        {"assumed_years_to_expiry": "0"},
        {"assumed_years_to_expiry": "5.1"},
        {"option_type": "CALL"},
    ],
    ids=["strike", "rate", "dividend", "expired", "horizon", "type"],
)
def test_scenario_domain(changes):
    with pytest.raises(ValueError):
        terms(**changes)


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), -1.0])
def test_numeric_model_rejects_invalid_volatility(value):
    with pytest.raises(ValueError):
        price_and_greeks(100, 100, 1, 0.05, 0.02, value, "CE")


def test_negative_rates_supported_as_explicit_assumptions():
    model = price_and_greeks(100, 100, 1, -0.01, 0.0, 0.2, "CE")
    value = compute_research_iv(
        spot_decimal="100",
        premium_decimal=f"{model.price:.12f}",
        terms=terms(annual_rate="-0.01", annual_dividend_yield="0"),
    )
    assert value.implied_volatility == pytest.approx(0.2, abs=1e-9)


def test_fingerprints_preserve_explicit_input_and_runtime():
    first = compute_research_iv(spot_decimal="100", premium_decimal="9.227005508154", terms=terms())
    same = compute_research_iv(spot_decimal="100", premium_decimal="9.227005508154", terms=terms())
    changed = compute_research_iv(
        spot_decimal="100.0", premium_decimal="9.227005508154", terms=terms()
    )
    assert first.calculation_id == same.calculation_id
    assert first.input_fingerprint != changed.input_fingerprint
    assert first.scipy_version and first.python_version
    assert scenario_terms_sha256(terms()) != scenario_terms_sha256(replace(terms(), strike="101"))


def test_extreme_moneyness_rejected_not_silent_zero_greeks():
    with pytest.raises(ValueError, match="BOUNDED_RESEARCH_BSM"):
        price_and_greeks(10000, 100, 1, 0.05, 0.02, 0.2, "CE")


def test_rho_and_theta_parity_with_dividends():
    call = price_and_greeks(105, 100, 0.75, 0.04, 0.015, 0.3, "CE")
    put = price_and_greeks(105, 100, 0.75, 0.04, 0.015, 0.3, "PE")
    assert call.rho_per_rate_unit - put.rho_per_rate_unit == pytest.approx(
        100 * 0.75 * math.exp(-0.04 * 0.75)
    )
    assert call.theta_per_calendar_day - put.theta_per_calendar_day == pytest.approx(
        (0.015 * 105 * math.exp(-0.015 * 0.75) - 0.04 * 100 * math.exp(-0.04 * 0.75)) / 365
    )


def test_zero_observation_not_replaced_with_artificial_premium():
    with pytest.raises(ValueError, match="PRICE_DOMAIN"):
        compute_research_iv(spot_decimal="100", premium_decimal="0", terms=terms())
