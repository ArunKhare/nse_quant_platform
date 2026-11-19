"""Pure exact-observation comparison, not numeric/native/source verification."""

import pytest

from nse_quant.data_platform.research_iv_observation import compare_iv_observations


def test_exact_observation_match_only():
    value = compare_iv_observations(b"exact", b"exact", b"exact")
    assert value.all_observations_match
    assert value.reason_codes == ()


@pytest.mark.parametrize(
    "first,second", [(b"bad", b"old"), (b"old", b"bad"), (b"bad", b"bad"), (b"one", b"two")]
)
def test_no_earlier_or_later_good_fallback(first, second):
    value = compare_iv_observations(b"old", first, second)
    assert not value.all_observations_match
    assert bool(value.reason_codes)
    assert value.recorded_matches_first is (first == b"old")
    assert value.recorded_matches_second is (second == b"old")
    assert value.fresh_observations_match is (first == second)


@pytest.mark.parametrize("changed", [b'"100.0"', b'"100.00"', b'"99.999999999999"'])
def test_no_numeric_or_decimal_tolerance(changed):
    assert not compare_iv_observations(b'"100"', changed, changed).all_observations_match


@pytest.mark.parametrize("position", [0, 1, 2])
@pytest.mark.parametrize(
    "bad",
    [
        pytest.param(b"", id="empty"),
        pytest.param(bytearray(b"x"), id="mutable"),
        pytest.param(b"x" * 1048577, id="oversized"),
    ],
)
def test_bounds_apply_to_every_observation(position, bad):
    values = [b"x", b"x", b"x"]
    values[position] = bad
    with pytest.raises(ValueError):
        compare_iv_observations(*values)


def test_maximum_immutable_observation():
    raw = b"x" * 1048576
    assert compare_iv_observations(raw, raw, raw).all_observations_match
