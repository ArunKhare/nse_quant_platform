import pytest

from nse_quant.core.iv_statistics import iv_percentile_and_rank


def test_ivp_uses_prior_strict_less_and_ivr_includes_current() -> None:
    ivp, ivr, count = iv_percentile_and_rank([0.10, 0.20, 0.30, 0.40], 0.30, lookback=5, minimum_history=4)
    assert ivp == 50.0
    assert ivr == pytest.approx(66.6666666667)
    assert count == 5


def test_ivr_uses_only_251_prior_values_plus_current() -> None:
    prior = [float(value) for value in range(1, 253)]
    ivp, ivr, count = iv_percentile_and_rank(prior, 253.0)
    assert ivp == 100.0
    assert ivr == 100.0
    assert count == 252


def test_insufficient_history_keeps_window_count_but_withholds_metrics() -> None:
    assert iv_percentile_and_rank([0.10, 0.20], 0.30) == (None, None, 3)


@pytest.mark.parametrize(
    ("prior", "current"),
    [([0.1, 0.2], float("nan")), ([0.1, float("inf")], 0.3), ([True], 0.3)],
)
def test_invalid_iv_values_rejected(prior: list[float], current: float) -> None:
    with pytest.raises(ValueError):
        iv_percentile_and_rank(prior, current)


def test_degenerate_rank_range_returns_no_ivr() -> None:
    assert iv_percentile_and_rank([0.2] * 120, 0.2) == (0.0, None, 121)
