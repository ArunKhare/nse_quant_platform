from nse_quant.research.regimes import (
    classify_iv,
    classify_regime,
    classify_trend,
    classify_volatility,
)


def test_trend_uses_atr_normalized_distance() -> None:
    assert classify_trend(101, 100, 1) == "BULL"
    assert classify_trend(99, 100, 1) == "BEAR"
    assert classify_trend(100.5, 100, 1) == "RANGE"
    assert classify_trend(100, None, 1) == "UNKNOWN"


def test_volatility_and_iv_buckets() -> None:
    assert classify_volatility(0.5, 85) == "HIGH"
    assert classify_volatility(0.1, 15) == "LOW"
    assert classify_volatility(0.2, 50) == "NORMAL"

    assert classify_iv(80, None) == "HIGH"
    assert classify_iv(20, None) == "LOW"
    assert classify_iv(50, None) == "NORMAL"
    assert classify_iv(None, None) == "UNKNOWN"


def test_combined_regime_is_point_in_time_label() -> None:
    result = classify_regime(
        close=101,
        sma50=100,
        atr14=1,
        realized_volatility=0.2,
        rv_percentile=50,
        iv_rank=80,
        iv_percentile=80,
    )

    assert result.trend_regime == "BULL"
    assert result.volatility_regime == "NORMAL"
    assert result.iv_regime == "HIGH"
    assert result.regime == "BULL|HIGH"
