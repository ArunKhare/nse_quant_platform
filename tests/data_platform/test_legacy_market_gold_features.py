"""Executable independent kernel tests; not native producer/reader E2E."""

import math
from fractions import Fraction

import pytest

from nse_quant.data_platform.legacy_market_gold_features import GeometryRejected, price_geometry


def fields(table="spot_candles", **changes):
    values = (
        dict(open=10.0, high=15.0, low=8.0, close=12.0)
        if table == "spot_candles"
        else dict(bid=10.0, ask=12.0, ltp=11.5, spot=101.0, strike=100.0)
    )
    result = {k: None if v is None else v.hex() for k, v in values.items()}
    result.update(changes)
    return result


def value(result, name):
    ratio = result["features"][name]
    if ratio["status"] == "UNAVAILABLE":
        assert ratio["numerator"] is None and ratio["denominator"] is None
        return None
    assert ratio["status"] == "COMPUTED"
    numerator, denominator = int(ratio["numerator"]), int(ratio["denominator"])
    assert denominator > 0 and math.gcd(numerator, denominator) == 1
    return Fraction(numerator, denominator)


def test_candle_geometry_exact():
    result = price_geometry(fields(), table="spot_candles")
    assert value(result, "high_minus_low") == 7
    assert value(result, "close_minus_open") == 2
    assert value(result, "upper_shadow") == 3
    assert value(result, "lower_shadow") == 2
    assert result["quality_flags"] == []


def test_option_geometry_exact_and_legacy_analytics_ignored():
    source = fields("option_stream")
    result = price_geometry(source, table="option_stream")
    assert value(result, "ask_minus_bid") == 2
    assert value(result, "bid_ask_midpoint") == 11
    assert value(result, "ltp_minus_midpoint") == Fraction(1, 2)
    assert value(result, "spot_minus_strike") == 1
    source["iv"] = "not-a-native-input"
    assert price_geometry(source, table="option_stream") == result


@pytest.mark.parametrize(
    "field", ["open", "high", "low", "close"], ids=["open", "high", "low", "close"]
)
def test_missing_operand_not_zero_imputed(field):
    result = price_geometry(fields(**{field: None}), table="spot_candles")
    assert "MISSING_" + field.upper() in result["quality_flags"]
    affected = {
        "open": ("close_minus_open", "upper_shadow", "lower_shadow"),
        "close": ("close_minus_open", "upper_shadow", "lower_shadow"),
        "high": ("high_minus_low", "upper_shadow"),
        "low": ("high_minus_low", "lower_shadow"),
    }
    for name in affected[field]:
        assert value(result, name) is None


@pytest.mark.parametrize(
    "field", ["bid", "ask", "ltp", "spot", "strike"], ids=["bid", "ask", "ltp", "spot", "strike"]
)
def test_missing_option_operands(field):
    result = price_geometry(fields("option_stream", **{field: None}), table="option_stream")
    assert "MISSING_" + field.upper() in result["quality_flags"]
    affected = {
        "bid": ("ask_minus_bid", "bid_ask_midpoint", "ltp_minus_midpoint"),
        "ask": ("ask_minus_bid", "bid_ask_midpoint", "ltp_minus_midpoint"),
        "ltp": ("ltp_minus_midpoint",),
        "spot": ("spot_minus_strike",),
        "strike": ("spot_minus_strike",),
    }
    for name in affected[field]:
        assert value(result, name) is None


@pytest.mark.parametrize(
    "bad",
    ["nan", "inf", "1.0", "0x1p+0", True, 1, "x" * 65537],
    ids=["nan", "inf", "decimal", "shorthex", "bool", "int", "oversized"],
)
def test_exact_finite_canonical_stored_binary64_only(bad):
    with pytest.raises(GeometryRejected, match="BINARY64"):
        price_geometry(fields(open=bad), table="spot_candles")


def test_binary64_values_not_decimal_price_recovery():
    result = price_geometry(
        fields("option_stream", bid=(0.1).hex(), ask=(0.2).hex()), table="option_stream"
    )
    assert value(result, "bid_ask_midpoint") == Fraction(10808639105689191, 72057594037927936)
    assert value(result, "bid_ask_midpoint") != Fraction(3, 20)


def test_extreme_midpoint_avoids_binary64_intermediate_overflow():
    maximum = float.fromhex("0x1.fffffffffffffp+1023")
    result = price_geometry(
        fields("option_stream", bid=maximum.hex(), ask=maximum.hex()), table="option_stream"
    )
    assert value(result, "bid_ask_midpoint") == Fraction.from_float(maximum)
    assert value(result, "ask_minus_bid") == 0


def test_subnormal_midpoint_is_exact_below_float_domain():
    tiny = float.fromhex("0x0.0000000000001p-1022")
    result = price_geometry(
        fields("option_stream", bid=(0.0).hex(), ask=tiny.hex()), table="option_stream"
    )
    assert value(result, "bid_ask_midpoint") == Fraction(1, 2**1075)


@pytest.mark.parametrize("zero", [0.0, -0.0], ids=["positive", "negative"])
def test_rational_zero_normalized_without_claiming_source_sign(zero):
    source = fields("option_stream", bid=zero.hex(), ask=zero.hex())
    result = price_geometry(source, table="option_stream")
    assert value(result, "bid_ask_midpoint") == 0
    assert "ZERO_BID" in result["quality_flags"]
    assert source["bid"] == zero.hex()


def test_invalid_geometry_retained_and_flagged_not_clipped():
    result = price_geometry(fields(high=(7.0).hex(), low=(9.0).hex()), table="spot_candles")
    assert value(result, "high_minus_low") == -2
    assert value(result, "upper_shadow") == -5
    assert "INVERTED_HIGH_LOW" in result["quality_flags"]
    assert "OPEN_OUTSIDE_STORED_RANGE" in result["quality_flags"]
    assert "CLOSE_OUTSIDE_STORED_RANGE" in result["quality_flags"]


def test_crossed_negative_quote_is_not_repaired():
    result = price_geometry(
        fields("option_stream", bid=(2.0).hex(), ask=(-1.0).hex()), table="option_stream"
    )
    assert value(result, "ask_minus_bid") == -3
    assert "NEGATIVE_ASK" in result["quality_flags"]
    assert "CROSSED_STORED_BID_ASK" in result["quality_flags"]


def test_unknown_profile_and_missing_explicit_field_refuse():
    with pytest.raises(GeometryRejected, match="PROFILE"):
        price_geometry(fields(), table="unknown")
    source = fields()
    del source["close"]
    with pytest.raises(GeometryRejected, match="FIELDS"):
        price_geometry(source, table="spot_candles")


def test_all_missing_yields_explicit_unavailable_features():
    source: dict[str, object] = {k: None for k in ("open", "high", "low", "close")}
    result = price_geometry(source, table="spot_candles")
    assert len(result["features"]) == 4
    assert all(value(result, name) is None for name in result["features"])
