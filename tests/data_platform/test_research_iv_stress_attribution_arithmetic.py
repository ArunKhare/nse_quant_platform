"""Real new arithmetic over explicit synthetic scalars, not BSM or native computation mocks."""

from decimal import ROUND_FLOOR, localcontext
from typing import Any

import pytest

from nse_quant.data_platform.research_iv_stress_attribution import decompose_spot_move


def compute(**changes):
    values: dict[str, Any] = dict(
        base_spot_decimal="100.00",
        shocked_spot_decimal="101.00",
        baseline_delta=0.5,
        baseline_gamma=0.02,
        full_model_price_change=0.75,
    )
    values.update(changes)
    return decompose_spot_move(**values)


def test_known_first_and_second_order_decomposition():
    value = compute()
    assert value.spot_change_decimal == "1.00" and value.spot_change_float == 1.0
    assert value.delta_component == 0.5
    assert value.gamma_component == 0.01
    assert value.delta_gamma_approximation == 0.51
    assert value.delta_only_residual == 0.25
    assert value.second_order_residual == 0.75 - 0.51
    assert value.reconstruction_roundoff == (0.51 + (0.75 - 0.51)) - 0.75


def test_negative_spot_move_put_like_delta_and_positive_gamma():
    value = compute(
        shocked_spot_decimal="90",
        baseline_delta=-0.5,
        baseline_gamma=0.02,
        full_model_price_change=6.25,
    )
    assert value.spot_change_decimal == "-10.00"
    assert value.delta_component == 5.0 and value.gamma_component == 1.0
    assert value.delta_gamma_approximation == 6.0
    assert value.delta_only_residual == 1.25 and value.second_order_residual == 0.25


def test_zero_move_components_zero_and_residual_not_hidden():
    value = compute(shocked_spot_decimal="100.00", full_model_price_change=0.0)
    assert value.delta_component == value.gamma_component == value.second_order_residual == 0.0
    # Pure scalar arithmetic does not claim an untrusted full-price change is model truth.
    untrusted = compute(shocked_spot_decimal="100.00", full_model_price_change=1.0)
    assert untrusted.second_order_residual == 1.0


def test_exact_decimal_difference_independent_of_ambient_precision():
    with localcontext() as context:
        context.prec = 2
        value = compute(
            base_spot_decimal="123.123456789012", shocked_spot_decimal="123.1357691346909012"
        )
    assert value.spot_change_decimal == "0.0123123456789012"
    assert value.spot_change_float == float("0.0123123456789012")


def test_roundoff_exposed_not_forced_to_close():
    value = compute(baseline_delta=1e16, baseline_gamma=0.0, full_model_price_change=1.0)
    assert value.delta_gamma_approximation == 1e16
    assert value.second_order_residual == -1e16
    assert value.reconstruction_roundoff == -1.0


def test_large_residual_is_not_an_accuracy_rejection():
    value = compute(full_model_price_change=100.0)
    assert value.second_order_residual == 100.0 - 0.51


@pytest.mark.parametrize(
    "field",
    ["baseline_delta", "baseline_gamma", "full_model_price_change"],
    ids=["delta", "gamma", "full-change"],
)
@pytest.mark.parametrize(
    "bad",
    [True, "1", None, float("nan"), float("inf")],
    ids=["bool", "text", "none", "nan", "infinite"],
)
def test_nonfinite_or_wrong_scalar_type_rejected(field, bad):
    with pytest.raises(ValueError, match="FINITE_NUMERIC"):
        compute(**{field: bad})


def test_negative_gamma_and_nonfinite_intermediates_rejected():
    with pytest.raises(ValueError, match="FINITE_NUMERIC"):
        compute(baseline_gamma=-1.0)
    with pytest.raises(ValueError, match="ARITHMETIC_NONFINITE"):
        compute(shocked_spot_decimal="150", baseline_delta=1e308)
    with pytest.raises(ValueError, match="ARITHMETIC_NONFINITE"):
        compute(shocked_spot_decimal="150", baseline_gamma=1e308)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("base_spot_decimal", "01"),
        ("base_spot_decimal", "1e2"),
        ("base_spot_decimal", "1.1234567890123"),
        ("shocked_spot_decimal", "NaN"),
        ("shocked_spot_decimal", "1.12345678901234567"),
        ("shocked_spot_decimal", 100),
        ("base_spot_decimal", "0"),
        ("base_spot_decimal", "1000000001"),
        ("shocked_spot_decimal", "49"),
        ("shocked_spot_decimal", "151"),
    ],
    ids=[
        "leading",
        "exponent",
        "base-precision",
        "nan-text",
        "derived-precision",
        "number",
        "zero",
        "high",
        "below-factor",
        "above-factor",
    ],
)
def test_coordinate_profile_not_normalized_or_clamped(field, bad):
    with pytest.raises(ValueError):
        compute(**{field: bad})


def test_decimal_rounding_and_exponent_context_are_explicit():
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_FLOOR
        context.Emax = 2
        value = compute(
            base_spot_decimal="1000000", shocked_spot_decimal="1000000", full_model_price_change=0.0
        )
    assert value.spot_change_decimal == "0"
    assert value.spot_change_float.hex() == (0.0).hex()
