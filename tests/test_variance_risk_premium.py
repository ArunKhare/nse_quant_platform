import pytest

from nse_quant.research.variance_risk_premium import (
    VRP_CALCULATION_VERSION,
    evaluate_variance_risk_premium,
)


def test_positive_vrp_passes() -> None:
    result = evaluate_variance_risk_premium(
        implied_volatility=0.20,
        expected_realized_volatility=0.15,
    )

    assert result.available is True
    assert result.passed is True
    assert result.variance_risk_premium == pytest.approx(0.04 - 0.0225)
    assert result.calculation_version == VRP_CALCULATION_VERSION
    assert result.reasons == []


def test_zero_vrp_passes_at_default_minimum() -> None:
    result = evaluate_variance_risk_premium(
        implied_volatility=0.20,
        expected_realized_volatility=0.20,
    )

    assert result.available is True
    assert result.passed is True
    assert result.variance_risk_premium == 0.0


def test_negative_vrp_fails() -> None:
    result = evaluate_variance_risk_premium(
        implied_volatility=0.15,
        expected_realized_volatility=0.20,
    )

    assert result.available is True
    assert result.passed is False
    assert result.variance_risk_premium < 0
    assert "variance_risk_premium_below_minimum" in result.reasons


def test_missing_iv_is_unavailable_not_failed() -> None:
    result = evaluate_variance_risk_premium(
        implied_volatility=None,
        expected_realized_volatility=0.15,
    )

    assert result.available is False
    assert result.passed is False
    assert result.variance_risk_premium is None
    assert "implied_volatility_unavailable" in result.reasons


def test_missing_rv_is_unavailable_not_failed() -> None:
    result = evaluate_variance_risk_premium(
        implied_volatility=0.20,
        expected_realized_volatility=None,
    )

    assert result.available is False
    assert result.passed is False
    assert result.variance_risk_premium is None
    assert "expected_realized_volatility_unavailable" in result.reasons


def test_negative_inputs_are_unavailable() -> None:
    result = evaluate_variance_risk_premium(
        implied_volatility=-0.1,
        expected_realized_volatility=-0.1,
    )

    assert result.available is False
    assert result.passed is False
    assert "implied_volatility_invalid" in result.reasons
    assert "expected_realized_volatility_invalid" in result.reasons
