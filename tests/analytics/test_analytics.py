from nse_quant.analytics.features import iv_rank, realized_volatility
from nse_quant.analytics.option_analytics import (
    bs_price_greeks,
    implied_volatility,
)


def test_bs_iv_roundtrip():
    price, *_ = bs_price_greeks(
        25000,
        25000,
        7 / 365,
        0.07,
        0.15,
        "CE",
    )

    solved_iv = implied_volatility(
        price,
        25000,
        25000,
        7 / 365,
        0.07,
        "CE",
    )

    assert solved_iv is not None
    assert abs(solved_iv - 0.15) < 1e-5


def test_iv_rank():
    assert iv_rank(16, [10, 12, 14, 16, 18]) == 75


def test_realized_volatility():
    closes = [100 + index for index in range(30)]

    assert realized_volatility(closes) is not None
