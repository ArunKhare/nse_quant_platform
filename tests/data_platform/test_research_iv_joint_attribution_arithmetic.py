"""Actual new vega arithmetic over explicit scalars, not mocked BSM/native computations."""

from decimal import ROUND_FLOOR, Decimal, localcontext
from typing import Any

import pytest

from nse_quant.data_platform.research_iv_joint_attribution import decompose_vega_residual


def compute(**changes):
    args: dict[str, Any] = dict(
        base_volatility=0.25,
        shifted_volatility=0.5,
        baseline_vega_per_vol_unit=40.0,
        spot_taylor_price_change=2.0,
        full_model_price_change=12.5,
    )
    args.update(changes)
    return decompose_vega_residual(**args)


def test_known_vega_units_and_joint_residual():
    value = compute()
    assert Decimal(value.effective_sigma_change_decimal) == Decimal("0.25")
    assert value.effective_sigma_change_float == 0.25
    assert value.vega_component == 10.0
    assert value.delta_gamma_vega_approximation == 12.0
    assert value.joint_residual == 0.5 and value.reconstruction_roundoff == 0.0
    assert value.base_sigma_hex == (0.25).hex()
    assert value.shifted_sigma_hex == (0.5).hex()


def test_negative_sigma_change_has_signed_vega_contribution():
    value = compute(base_volatility=0.5, shifted_volatility=0.25, full_model_price_change=-7.5)
    assert value.vega_component == -10.0
    assert value.delta_gamma_vega_approximation == -8.0
    assert value.joint_residual == 0.5


def test_effective_float_delta_not_nominal_decimal_offset():
    base, shifted = 0.2, 0.21000000000000002
    value = compute(base_volatility=base, shifted_volatility=shifted)
    with localcontext() as context:
        context.prec = 128
        expected = Decimal.from_float(shifted) - Decimal.from_float(base)
    assert Decimal(value.effective_sigma_change_decimal) == expected
    assert value.effective_sigma_change_float == shifted - base
    assert Decimal(value.effective_sigma_change_decimal) != Decimal("0.01")


def test_zero_sigma_change_preserves_spot_approximation():
    value = compute(
        shifted_volatility=0.25, spot_taylor_price_change=2.0, full_model_price_change=2.125
    )
    assert value.vega_component == 0.0
    assert value.delta_gamma_vega_approximation == 2.0
    assert value.joint_residual == 0.125


def test_explicit_decimal_context_independent_of_caller():
    original = compute(base_volatility=0.2, shifted_volatility=0.21)
    with localcontext() as context:
        context.prec = 2
        context.Emax = 1
        context.rounding = ROUND_FLOOR
        changed = compute(base_volatility=0.2, shifted_volatility=0.21)
    assert original == changed


def test_large_residual_and_roundoff_are_not_corrected():
    value = compute(
        shifted_volatility=0.25, spot_taylor_price_change=1e16, full_model_price_change=1.0
    )
    assert value.joint_residual == -1e16
    assert value.reconstruction_roundoff == -1.0


@pytest.mark.parametrize(
    "field", ["base_volatility", "shifted_volatility"], ids=["base", "shifted"]
)
@pytest.mark.parametrize(
    "bad",
    [True, 1, "0.2", None, float("nan"), float("inf"), 0.0, 5.1],
    ids=["bool", "int", "text", "none", "nan", "infinite", "low", "high"],
)
def test_bounded_float_model_coordinates_required(field, bad):
    with pytest.raises(ValueError, match="BOUNDED_FLOAT_SIGMAS"):
        compute(**{field: bad})


@pytest.mark.parametrize(
    "field",
    ["baseline_vega_per_vol_unit", "spot_taylor_price_change", "full_model_price_change"],
    ids=["vega", "spot", "full"],
)
@pytest.mark.parametrize(
    "bad",
    [True, "1", None, float("nan"), float("inf")],
    ids=["bool", "text", "none", "nan", "infinite"],
)
def test_finite_scalar_types_required(field, bad):
    with pytest.raises(ValueError, match="FINITE_NUMBER"):
        compute(**{field: bad})


def test_negative_vega_and_nonfinite_intermediates_fail_closed():
    with pytest.raises(ValueError, match="FINITE_NUMBER"):
        compute(baseline_vega_per_vol_unit=-1.0)
    with pytest.raises(ValueError, match="NONFINITE_ARITHMETIC"):
        compute(base_volatility=0.25, shifted_volatility=5.0, baseline_vega_per_vol_unit=1e308)


def test_original_kernel_binary_lower_endpoint_is_supported():
    value = compute(base_volatility=0.000001, shifted_volatility=0.000001)
    assert value.effective_sigma_change_float == 0.0
