import math

import pytest

from nse_quant.research.variance_risk_premium import (
    EXPECTED_RV_VERSION,
    VRP_CALCULATION_VERSION,
    evaluate_variance_risk_premium,
    trailing_daily_realized_volatility,
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


@pytest.mark.parametrize("volatility", [0.0, 0.20, 0.50])
def test_zero_vrp_fails_at_default_minimum(volatility: float) -> None:
    result = evaluate_variance_risk_premium(
        implied_volatility=volatility,
        expected_realized_volatility=volatility,
    )
    assert result.available is True
    assert result.passed is False
    assert result.variance_risk_premium == 0.0
    assert result.reasons == ["variance_risk_premium_at_minimum"]


def test_negative_vrp_fails() -> None:
    result = evaluate_variance_risk_premium(
        implied_volatility=0.15,
        expected_realized_volatility=0.20,
    )
    assert result.available is True
    assert result.passed is False
    assert result.variance_risk_premium < 0
    assert "variance_risk_premium_below_minimum" in result.reasons


@pytest.mark.parametrize(
    "minimum,passed,reason",
    [
        (math.nextafter(0.0625, -math.inf), True, None),
        (0.0625, False, "variance_risk_premium_at_minimum"),
        (math.nextafter(0.0625, math.inf), False, "variance_risk_premium_below_minimum"),
    ],
)
def test_positive_minimum_boundary_is_strict(minimum, passed, reason) -> None:
    result = evaluate_variance_risk_premium(
        implied_volatility=0.25,
        expected_realized_volatility=0.0,
        minimum_vrp=minimum,
    )
    assert result.available is True
    assert result.variance_risk_premium == 0.0625
    assert result.passed is passed
    assert result.reasons == ([] if reason is None else [reason])


def test_tiny_positive_vrp_is_not_rounded_to_zero() -> None:
    result = evaluate_variance_risk_premium(
        implied_volatility=math.nextafter(0.25, math.inf),
        expected_realized_volatility=0.25,
    )
    assert result.available is True
    assert result.variance_risk_premium > 0.0
    assert result.passed is True


def test_tiny_negative_vrp_does_not_pass() -> None:
    result = evaluate_variance_risk_premium(
        implied_volatility=math.nextafter(0.25, -math.inf),
        expected_realized_volatility=0.25,
    )
    assert result.available is True
    assert result.variance_risk_premium < 0.0
    assert result.passed is False


def test_strict_gate_policy_is_auditable_without_changing_formula_version() -> None:
    result = evaluate_variance_risk_premium(
        implied_volatility=0.20, expected_realized_volatility=0.20
    )
    assert result.calculation_version == "variance_risk_premium_v1"
    assert result.details["threshold_comparison"] == ">"
    assert result.details["gate_version"] == "variance_risk_premium_gate_strict_v1"
    assert result.details["minimum_vrp"] == 0.0


def test_missing_iv_is_unavailable_not_failed() -> None:
    result = evaluate_variance_risk_premium(
        implied_volatility=None, expected_realized_volatility=0.15
    )
    assert result.available is False
    assert result.passed is False
    assert result.variance_risk_premium is None
    assert "implied_volatility_unavailable" in result.reasons


def test_missing_rv_is_unavailable_not_failed() -> None:
    result = evaluate_variance_risk_premium(
        implied_volatility=0.20, expected_realized_volatility=None
    )
    assert result.available is False
    assert result.passed is False
    assert result.variance_risk_premium is None
    assert "expected_realized_volatility_unavailable" in result.reasons


def test_negative_inputs_are_unavailable() -> None:
    result = evaluate_variance_risk_premium(
        implied_volatility=-0.1, expected_realized_volatility=-0.1
    )
    assert result.available is False
    assert result.passed is False
    assert "implied_volatility_invalid" in result.reasons
    assert "expected_realized_volatility_invalid" in result.reasons


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf, True, False])
@pytest.mark.parametrize("input_name", ["implied_volatility", "expected_realized_volatility"])
def test_invalid_input_remains_unavailable(invalid, input_name) -> None:
    inputs = {"implied_volatility": 0.20, "expected_realized_volatility": 0.15}
    inputs[input_name] = invalid
    result = evaluate_variance_risk_premium(**inputs)
    assert result.available is False
    assert result.passed is False
    assert result.variance_risk_premium is None
    assert f"{input_name}_invalid" in result.reasons


def test_trailing_daily_rv_matches_manual_calculation() -> None:
    closes = [100.0, 101.0, 100.0, 102.0, 101.0, 103.0]
    rv, details = trailing_daily_realized_volatility(closes, window_days=5)
    returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    mean = sum(returns) / len(returns)
    expected = math.sqrt(sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)) * math.sqrt(252)
    assert rv == pytest.approx(expected)
    assert details["version"] == EXPECTED_RV_VERSION
    assert details["closes_required"] == 6


def test_trailing_daily_rv_unavailable_with_too_few_closes() -> None:
    rv, details = trailing_daily_realized_volatility([100.0, 101.0], window_days=5)
    assert rv is None
    assert details["reason"] == "insufficient_daily_closes"
