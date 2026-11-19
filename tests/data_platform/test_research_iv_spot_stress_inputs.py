"""Exact arithmetic/input tests; no substituted native computations or model claims."""

from decimal import Decimal, localcontext

import pytest

from nse_quant.data_platform.research_iv_spot_stress import (
    shocked_spot_decimal,
    validate_shocks,
)


@pytest.mark.parametrize(
    "shocks",
    [(), (0,) * 17, [0], (True,), (1.0,), (-5001,), (5001,), (0, 0), (1, 0), None],
    ids=[
        "empty",
        "count",
        "mutable",
        "bool",
        "float",
        "low",
        "high",
        "duplicate",
        "unsorted",
        "none",
    ],
)
def test_bad_shock_request_rejected(shocks):
    with pytest.raises(ValueError):
        validate_shocks(shocks)


def test_inclusive_grid_bounds_and_exact_tuple():
    shocks = (-5000, -1, 0, 1, 5000)
    assert validate_shocks(shocks) is shocks
    assert validate_shocks(tuple(range(16))) == tuple(range(16))


@pytest.mark.parametrize(
    "spot",
    [
        "0",
        "-1",
        "01",
        "1e2",
        "NaN",
        "Infinity",
        "1000000001",
        "0.000000001",
        "1.1234567890123",
        "",
        100,
        True,
    ],
    ids=[
        "zero",
        "negative",
        "leading",
        "exponent",
        "nan",
        "infinite",
        "high",
        "low",
        "precision",
        "empty",
        "number",
        "bool",
    ],
)
def test_bad_original_spot_rejected(spot):
    with pytest.raises(ValueError):
        shocked_spot_decimal(spot, 0)


@pytest.mark.parametrize(
    "spot,bps,expected",
    [
        ("100.00", 100, "101.00"),
        ("100.00", -100, "99.00"),
        ("123.123456789012", 1, "123.1357691346909012"),
        ("100", -5000, "50"),
        ("100", 5000, "150"),
        ("0.00000001", 0, "0.00000001"),
        ("1000000000", 0, "1000000000"),
    ],
    ids=["up", "down", "exact-fraction", "low-shock", "high-shock", "low-spot", "high-spot"],
)
def test_exact_derived_spots(spot, bps, expected):
    assert shocked_spot_decimal(spot, bps) == expected


def test_decimal_context_does_not_round_results():
    with localcontext() as context:
        context.prec = 2
        assert shocked_spot_decimal("123.123456789012", 1) == "123.1357691346909012"
    assert Decimal(shocked_spot_decimal("100.00", 100)) == Decimal("101")


@pytest.mark.parametrize(
    "spot,shock", [("0.00000001", -1), ("1000000000", 1)], ids=["below-domain", "above-domain"]
)
def test_outside_domain_is_not_clamped(spot, shock):
    with pytest.raises(ValueError, match="DERIVED_SPOT_OUTSIDE_DOMAIN"):
        shocked_spot_decimal(spot, shock)
