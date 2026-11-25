import math

import pytest

from nse_quant.research.variance_risk_premium import (
    EXPECTED_RV_VERSION,
    HAR_RV_HORIZON_DAYS,
    HAR_RV_MEASURE,
    HAR_RV_METHOD,
    HAR_RV_VERSION,
    VRP_CALCULATION_VERSION,
    evaluate_variance_risk_premium,
    trailing_daily_realized_volatility,
)


def har_forecast_identity() -> dict:
    return {
        "expected_realized_volatility_method": HAR_RV_METHOD,
        "expected_realized_volatility_version": HAR_RV_VERSION,
        "expected_realized_volatility_horizon_days": HAR_RV_HORIZON_DAYS,
        "expected_realized_volatility_measure": HAR_RV_MEASURE,
        "expected_realized_volatility_is_forecast": True,
        "expected_realized_volatility_calibration_is_eligible": True,
        "expected_realized_volatility_calibration_margin": 0.001,
        "implied_volatility_source": "india_vix_eod",
        "implied_volatility_is_30d_constant_maturity": True,
    }


def test_positive_vrp_passes_with_declared_har_forecast() -> None:
    result = evaluate_variance_risk_premium(
        implied_volatility=0.20,
        expected_realized_volatility=0.15,
        **har_forecast_identity(),
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
    assert "variance_risk_premium_at_minimum" in result.reasons
    assert "expected_rv_estimator_not_gate_eligible" in result.reasons


def test_positive_vrp_from_trailing_fallback_is_diagnostic_only() -> None:
    result = evaluate_variance_risk_premium(
        implied_volatility=0.30,
        expected_realized_volatility=0.10,
    )
    assert result.available is True
    assert result.variance_risk_premium == pytest.approx(0.08)
    assert result.passed is False
    assert result.details["estimator_gate_eligible"] is False
    assert "expected_rv_estimator_not_gate_eligible" in result.reasons


@pytest.mark.parametrize(
    "identity",
    [
        {"expected_realized_volatility_version": "wrong-version"},
        {"expected_realized_volatility_horizon_days": 20},
        {"expected_realized_volatility_measure": "close_to_close"},
        {"expected_realized_volatility_is_forecast": False},
        {"expected_realized_volatility_calibration_is_eligible": False},
        {"expected_realized_volatility_method": "unknown"},
        {"implied_volatility_is_30d_constant_maturity": False},
    ],
)
def test_incomplete_or_mismatched_har_identity_cannot_pass(identity: dict) -> None:
    result = evaluate_variance_risk_premium(
        implied_volatility=0.30,
        expected_realized_volatility=0.10,
        **(har_forecast_identity() | identity),
    )
    assert result.available is True
    assert result.passed is False
    assert "expected_rv_estimator_not_gate_eligible" in result.reasons


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
        **har_forecast_identity(),
    )
    assert result.available is True
    assert result.variance_risk_premium == 0.0625
    assert result.passed is passed
    assert result.reasons == ([] if reason is None else [reason])


def test_tiny_positive_vrp_is_not_rounded_to_zero() -> None:
    result = evaluate_variance_risk_premium(
        implied_volatility=math.nextafter(0.25, math.inf),
        expected_realized_volatility=0.25,
        **har_forecast_identity(),
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


def test_strict_har_only_gate_policy_is_auditable() -> None:
    result = evaluate_variance_risk_premium(
        implied_volatility=0.20, expected_realized_volatility=0.20
    )
    assert result.calculation_version == "variance_risk_premium_v4"
    assert result.details["threshold_comparison"] == ">"
    assert result.details["gate_version"] == "variance_risk_premium_gate_har_calibrated_iv30_v4"
    assert result.details["estimator_gate_eligible"] is False
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
    assert details["method"] == "trailing_close_close"
    assert details["gate_eligible"] is False
    assert details["diagnostic_only"] is True
    assert details["closes_required"] == 6


def test_trailing_daily_rv_unavailable_with_too_few_closes() -> None:
    rv, details = trailing_daily_realized_volatility([100.0, 101.0], window_days=5)
    assert rv is None
    assert details["reason"] == "insufficient_daily_closes"



def test_near_expiry_atm_iv_cannot_satisfy_vrp_gate() -> None:
    result = evaluate_variance_risk_premium(
        implied_volatility=0.30,
        expected_realized_volatility=0.10,
        **(har_forecast_identity() | {
            "implied_volatility_source": "features.atm_iv",
            "implied_volatility_is_30d_constant_maturity": False,
        }),
    )
    assert result.available is True
    assert result.details["estimator_gate_eligible"] is True
    assert result.details["implied_volatility_gate_eligible"] is False
    assert result.passed is False
    assert "implied_volatility_not_30d_constant_maturity" in result.reasons
