"""Independent exact retained-observation arithmetic/series tests, not native attestation."""

from datetime import UTC, datetime, timedelta
from fractions import Fraction

import pytest

from nse_quant.data_platform.legacy_candle_returns import adjacent_candle_features


def fields(prices, *, token="1", interval="1m", symbol="S"):
    at = datetime(2026, 1, 1, tzinfo=UTC)
    return tuple(
        dict(
            instrument_token=token,
            interval=interval,
            symbol=symbol,
            ts=(at + timedelta(seconds=i * 60)).isoformat(),
            close=None if p is None else float(p).hex(),
        )
        for i, p in enumerate(prices)
    )


def ratio(value):
    return dict(numerator=str(value.numerator), denominator=str(value.denominator))


def test_exact_return_not_original_decimal_or_regular_grid():
    result = adjacent_candle_features(fields([0.1, 0.3]))
    expected = (Fraction(0.3) - Fraction(0.1)) / Fraction(0.1)
    assert result[1]["simple_return"] == ratio(expected)
    assert result[1]["elapsed_stored_microseconds"] == "60000000"
    assert result[0]["simple_return"] is None


def test_chronological_sort_returns_original_ordinal_order():
    rows = fields([10, 20, 30])
    result = adjacent_candle_features((rows[2], rows[0], rows[1]))
    assert [r["predecessor_ordinal"] for r in result] == [2, None, 1]
    assert result[0]["simple_return"] == ratio(Fraction(1, 2))
    assert result[2]["simple_return"] == ratio(Fraction(1))


def test_missing_is_not_bridged():
    result = adjacent_candle_features(fields([10, None, 20, 30]))
    assert result[1]["simple_return"] is None
    assert result[2]["simple_return"] is None
    assert result[2]["predecessor_ordinal"] == 1
    assert result[3]["simple_return"] == ratio(Fraction(1, 2))


@pytest.mark.parametrize("zero", [0.0, -0.0], ids=["positive-zero", "negative-zero"])
def test_zero_denominator_not_imputed(zero):
    result = adjacent_candle_features(fields([zero, 10]))
    assert result[1]["simple_return"] is None
    assert result[1]["close_change"] == ratio(Fraction(10))
    assert "PREVIOUS_CLOSE_NONPOSITIVE" in result[1]["quality_flags"]


def test_negative_is_flagged_not_repaired():
    result = adjacent_candle_features(fields([-10, 20]))
    assert result[1]["simple_return"] == ratio(Fraction(-3))
    assert "PREVIOUS_CLOSE_NONPOSITIVE" in result[1]["quality_flags"]


def test_groups_do_not_mix_token_or_interval():
    a, b = fields([10, 20]), fields([100, 200], token="2")
    c = fields([5], interval="day")
    result = adjacent_candle_features((a[0], b[0], a[1], b[1], c[0]))
    assert [r["predecessor_ordinal"] for r in result] == [None, None, 0, 1, None]


def test_symbol_change_breaks_return_but_never_skips_source():
    rows = list(fields([10, 20, 40]))
    rows[1]["symbol"] = "OTHER"
    result = adjacent_candle_features(tuple(rows))
    assert result[1]["simple_return"] is None
    assert result[2]["simple_return"] is None
    assert result[2]["predecessor_ordinal"] == 1
    assert "SYMBOL_CHANGED_NO_BINDING" in result[2]["quality_flags"]


@pytest.mark.parametrize("symbol", [None, ""], ids=["null", "empty"])
def test_unknown_symbol_return_unavailable(symbol):
    result = adjacent_candle_features(fields([10, 20], symbol=symbol))
    assert result[1]["simple_return"] is None
    assert "SYMBOL_UNKNOWN" in result[1]["quality_flags"]


def test_unknown_interval_unavailable():
    result = adjacent_candle_features(fields([10, 20], interval=""))
    assert result[1]["simple_return"] is None
    assert "INTERVAL_UNKNOWN" in result[1]["quality_flags"]


def test_elapsed_gap_not_filled_or_annualized():
    rows = list(fields([10, 20]))
    rows[1]["ts"] = "2026-02-01T00:00:00+00:00"
    result = adjacent_candle_features(tuple(rows))
    assert result[1]["simple_return"] == ratio(Fraction(1))
    assert result[1]["elapsed_stored_microseconds"] == str(31 * 86400 * 1000000)


def test_duplicate_instant_no_winner():
    row = fields([10])[0]
    with pytest.raises(ValueError, match="DUPLICATE"):
        adjacent_candle_features((row, dict(row, close=(20.0).hex())))


@pytest.mark.parametrize(
    "value",
    ["nan", "inf", "0x1p+0", "-0x0p+0", "1.0"],
    ids=["nan", "infinity", "noncanonical", "zero-spelling", "decimal"],
)
def test_invalid_stored_close(value):
    row = fields([10])[0]
    row["close"] = value
    with pytest.raises(ValueError):
        adjacent_candle_features((row,))


@pytest.mark.parametrize(
    "ts", ["2026-01-01T00:00:00", "2026-01-01T05:30:00+05:30"], ids=["naive", "noncanonical-offset"]
)
def test_stored_utc_contract_not_silently_reassigned(ts):
    row = fields([10])[0]
    row["ts"] = ts
    with pytest.raises(ValueError, match="UTC"):
        adjacent_candle_features((row,))


@pytest.mark.parametrize("count", [0, 16001], ids=["empty", "overflow"])
def test_whole_series_count_bound(count):
    with pytest.raises(ValueError, match="ROW_BOUND"):
        adjacent_candle_features(({},) * count)


def test_extreme_binary64_exact_no_float_return_overflow():
    rows = fields(
        [float.fromhex("0x0.0000000000001p-1022"), float.fromhex("0x1.fffffffffffffp+1023")]
    )
    value = adjacent_candle_features(rows)[1]["simple_return"]
    assert value is not None
    assert len(value["numerator"]) > 600
    assert value["denominator"] == "1"
