"""Pure fixed-elapsed-window contracts, not market coverage or native source attestation."""

from datetime import UTC, datetime, timedelta
from fractions import Fraction

import pytest

from nse_quant.data_platform.legacy_return_windows import (
    ReturnWindowPolicy,
    _bounded,
    window_statistics,
)


def fields(prices, times=None):
    at = datetime(2026, 1, 1, tzinfo=UTC)
    times = list(range(len(prices))) if times is None else times
    return tuple(
        dict(
            instrument_token="1",
            interval="1m",
            symbol="S",
            ts=(at + timedelta(minutes=t)).isoformat(),
            close=None if p is None else float(p).hex(),
        )
        for p, t in zip(prices, times, strict=True)
    )


def compute(rows, n=2, cadence=60000000):
    return window_statistics(rows, policy=ReturnWindowPolicy(n, cadence))


def test_exact_squares_and_mean_not_standard_deviation():
    rows = compute(fields([10, 20, 30]))
    assert len(rows) == 3
    assert rows[0]["status"] == rows[1]["status"] == "UNAVAILABLE"
    assert rows[2]["sum_squared_simple_returns"] == dict(numerator="5", denominator="4")
    assert rows[2]["mean_squared_simple_returns"] == dict(numerator="5", denominator="8")
    assert rows[2]["policy_cadence_matched"]
    assert not rows[2]["authoritative_market_coverage_verified"]


def test_three_returns_requires_four_prices():
    result = compute(fields([1, 2, 4, 8]), n=3)
    assert result[-1]["sum_squared_simple_returns"] == dict(numerator="3", denominator="1")
    assert result[-1]["member_ordinals"] == [0, 1, 2, 3]


def test_gap_no_filtering_then_fully_consecutive_suffix_recovers():
    result = compute(fields([1, 2, 4, 8, 16], [0, 1, 10, 11, 12]))
    for index in (2, 3):
        assert result[index]["status"] == "UNAVAILABLE"
        assert "ELAPSED_CADENCE_MISMATCH" in result[index]["reason_codes"]
    assert result[4]["status"] == "COMPUTED_RESEARCH_WINDOW"
    assert result[4]["member_ordinals"] == [2, 3, 4]


def test_missing_no_bridge_and_exact_window_recovery():
    result = compute(fields([10, None, 20, 40, 80]))
    assert result[2]["sum_squared_simple_returns"] is None
    assert result[3]["sum_squared_simple_returns"] is None
    assert result[4]["sum_squared_simple_returns"] == dict(numerator="2", denominator="1")


@pytest.mark.parametrize("bad", [0.0, -0.0, -10.0], ids=["zero", "negative-zero", "negative"])
def test_strict_positive_window_domain(bad):
    result = compute(fields([10, bad, 20]))[-1]
    assert result["status"] == "UNAVAILABLE"
    assert "NONPOSITIVE_CLOSE_IN_WINDOW" in result["reason_codes"]
    assert result["mean_squared_simple_returns"] is None


def test_symbol_drift_not_hidden_by_equal_numeric_returns():
    rows = list(fields([1, 2, 4, 8]))
    rows[0]["symbol"] = "OTHER"
    result = compute(tuple(rows))
    assert result[2]["status"] == "UNAVAILABLE"
    assert result[3]["status"] == "COMPUTED_RESEARCH_WINDOW"


@pytest.mark.parametrize(
    "key,value",
    [("symbol", None), ("symbol", ""), ("interval", "")],
    ids=["null-symbol", "empty-symbol", "empty-interval"],
)
def test_unknown_group_semantics_unavailable(key, value):
    rows = fields([1, 2, 4])
    rows = tuple(dict(r, **{key: value}) for r in rows)
    assert compute(rows)[-1]["status"] == "UNAVAILABLE"


def test_original_source_order_preserved_after_chronological_sort():
    a, b, c = fields([10, 20, 30])
    result = compute((c, a, b))
    assert result[0]["member_ordinals"] == [1, 2, 0]
    assert result[0]["sum_squared_simple_returns"] == dict(numerator="5", denominator="4")


def test_groups_do_not_mix():
    a = fields([1, 2, 4])
    b = tuple(dict(r, instrument_token="2") for r in fields([1, 3, 9]))
    rows = (a[0], b[0], a[1], b[1], a[2], b[2])
    result = compute(rows)
    assert result[4]["member_ordinals"] == [0, 2, 4]
    assert result[5]["member_ordinals"] == [1, 3, 5]
    assert result[5]["sum_squared_simple_returns"] == dict(numerator="8", denominator="1")


@pytest.mark.parametrize(
    "n,cadence",
    [
        (True, 1),
        (1, 1),
        (257, 1),
        (2, True),
        (2, 0),
        (2, 86400000001),
    ],
    ids=["bool-count", "small-count", "large-count", "bool-cadence", "zero", "large-cadence"],
)
def test_exact_bounded_policy(n, cadence):
    with pytest.raises(ValueError):
        ReturnWindowPolicy(n, cadence)


def test_cadence_is_explicit_not_parsed_from_interval_label():
    result = compute(fields([1, 2, 4]), cadence=1)[-1]
    assert result["status"] == "UNAVAILABLE"
    assert "ELAPSED_CADENCE_MISMATCH" in result["reason_codes"]


def test_rational_resource_limit_is_whole_computation_refusal():
    assert _bounded(Fraction(1 << 8191)) == Fraction(1 << 8191)
    with pytest.raises(ValueError, match="RATIONAL_RESOURCE_BOUND"):
        _bounded(Fraction(1 << 8192))


def test_policy_type_is_not_caller_dict():
    with pytest.raises(TypeError):
        window_statistics(fields([1, 2, 4]), policy={})


def test_duplicate_instant_rejects_entire_series():
    rows = fields([1, 2, 4])
    with pytest.raises(ValueError, match="DUPLICATE"):
        compute((rows[0], rows[0], rows[2]))


@pytest.mark.parametrize("count", [0, 16001], ids=["empty", "overflow"])
def test_independent_whole_row_bound(count):
    with pytest.raises(ValueError, match="ROW_BOUND"):
        compute(({},) * count)


def test_time_match_is_distinct_from_price_domain_validity():
    row = compute(fields([1, None, 4]))[-1]
    assert row["policy_cadence_matched"]
    assert not row["policy_window_satisfied"]
    assert row["status"] == "UNAVAILABLE"
