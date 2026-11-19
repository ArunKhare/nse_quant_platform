"""Actual new volatility-coordinate arithmetic; not native/model success substitutes."""

from decimal import ROUND_FLOOR, Decimal, localcontext

import pytest

from nse_quant.data_platform.research_iv_spot_vol_surface import (
    VOL_HIGH,
    VOL_LOW,
    shifted_volatility,
    validate_vol_shifts,
)


@pytest.mark.parametrize(
    "bad",
    [(), [0], (True,), (1.0,), (0,) * 9, (0, 0), (1, 0), (-5001,), (5001,), None],
    ids=["empty", "mutable", "bool", "float", "count", "duplicate", "order", "low", "high", "none"],
)
def test_vol_grid_profile(bad):
    with pytest.raises(ValueError):
        validate_vol_shifts(bad)


def test_inclusive_grid_bounds_and_identity():
    grid = (-5000, 0, 5000)
    assert validate_vol_shifts(grid) is grid
    assert validate_vol_shifts(tuple(range(8))) == tuple(range(8))


@pytest.mark.parametrize("sigma", [VOL_LOW, 0.2, VOL_HIGH], ids=["low", "ordinary", "high"])
def test_zero_shift_preserves_original_float_bits_and_exact_origin(sigma):
    value = shifted_volatility(sigma, 0)
    assert value.value.hex() == sigma.hex() == value.value_hex
    assert Decimal(value.exact_decimal) == Decimal.from_float(sigma)


@pytest.mark.parametrize(
    "shift",
    [-1000, -1, 1, 100, 1000],
    ids=["down-large", "down-small", "up-small", "one-percent-point", "up-large"],
)
def test_offsets_are_absolute_exact_decimal_not_relative(shift):
    value = shifted_volatility(0.5, shift)
    expected = Decimal("0.5") + Decimal(shift) / Decimal(10000)
    assert Decimal(value.exact_decimal) == expected
    assert value.value == float(expected)
    assert value.value_hex == value.value.hex()


def test_decimal_float_origin_is_not_rounded_to_shortest_decimal():
    value = shifted_volatility(0.2, -1000)
    with localcontext() as context:
        context.prec = 128
        expected = Decimal.from_float(0.2) - Decimal("0.1")
    assert Decimal(value.exact_decimal) == expected
    assert value.value == float(expected)
    assert Decimal(value.exact_decimal) != Decimal("0.1")


def test_original_binary_lower_bound_is_not_replaced_by_decimal_literal():
    value = shifted_volatility(VOL_LOW, 0)
    assert value.value == VOL_LOW
    assert Decimal(value.exact_decimal) == Decimal.from_float(VOL_LOW)


@pytest.mark.parametrize(
    "sigma,shift",
    [(VOL_LOW, -1), (VOL_HIGH, 1), (0.2, -5000)],
    ids=["below-low", "above-high", "negative-derived"],
)
def test_out_of_domain_coordinates_raise_without_clamping(sigma, shift):
    with pytest.raises(ValueError, match="OUTSIDE_KERNEL_BRACKET"):
        shifted_volatility(sigma, shift)


@pytest.mark.parametrize(
    "bad",
    [True, 1, None, "0.2", float("nan"), float("inf"), 0.0, 5.1],
    ids=["bool", "int", "none", "text", "nan", "infinite", "low", "high"],
)
def test_invalid_original_sigma_rejected(bad):
    with pytest.raises(ValueError):
        shifted_volatility(bad, 0)


def test_decimal_context_does_not_change_shift():
    original = shifted_volatility(0.2, 1)
    with localcontext() as context:
        context.prec = 2
        context.Emax = 1
        context.rounding = ROUND_FLOOR
        changed = shifted_volatility(0.2, 1)
    assert changed == original


@pytest.mark.parametrize(
    "bad", [True, 1.0, "1", None, -5001, 5001], ids=["bool", "float", "text", "none", "low", "high"]
)
def test_direct_shift_type_and_bound(bad):
    with pytest.raises(ValueError):
        shifted_volatility(0.2, bad)
