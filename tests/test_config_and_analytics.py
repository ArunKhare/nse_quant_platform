import pytest

from nse_quant.analytics.features import iv_rank, realized_volatility
from nse_quant.analytics.option_analytics import bs_price_greeks, implied_volatility
from nse_quant.core.settings import Settings


def test_settings_blocks_live_mode():
    with pytest.raises(ValueError):
        Settings(
            safety={
                "trading_enabled": True,
                "dry_run": False,
                "paper_trading": False,
            }
        )


def test_bs_iv_roundtrip():
    price, *_ = bs_price_greeks(25000, 25000, 7 / 365, 0.07, 0.15, "CE")
    assert abs(implied_volatility(price, 25000, 25000, 7 / 365, 0.07, "CE") - 0.15) < 1e-5


def test_iv_rank():
    assert iv_rank(16, [10, 12, 14, 16, 18]) == 75


def test_rv():
    assert realized_volatility([100 + i for i in range(30)]) is not None
