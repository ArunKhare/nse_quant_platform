"""Tests for stock context features."""

from __future__ import annotations

import numpy as np
import pandas as pd

from nse_quant.research.stock_context_features import (
    ContextSettings,
    build_context_features,
    classify_sector_regime,
    compute_beta,
    compute_correlation,
    compute_market_breadth,
    compute_relative_strength,
)


def _returns(n: int, seed: int = 42):
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(0.0005, 0.01, n))


def test_compute_beta_basic():
    stock = _returns(300)
    bench = _returns(300, seed=7)
    beta = compute_beta(stock, bench, window=252)
    assert beta is not None
    assert -5.0 < beta < 5.0


def test_compute_beta_insufficient_data():
    stock = _returns(100)
    bench = _returns(100)
    assert compute_beta(stock, bench, window=252) is None


def test_compute_correlation_basic():
    stock = _returns(300)
    bench = _returns(300, seed=7)
    corr = compute_correlation(stock, bench, window=252)
    assert corr is not None
    assert -1.0 <= corr <= 1.0


def test_compute_relative_strength_basic():
    stock = _returns(300)
    bench = _returns(300, seed=7)
    rs = compute_relative_strength(stock, bench, window=252)
    assert rs is not None


def test_classify_sector_regime():
    assert classify_sector_regime(0.10) == "OUTPERFORMING"
    assert classify_sector_regime(-0.10) == "UNDERPERFORMING"
    assert classify_sector_regime(0.01) == "NEUTRAL"
    assert classify_sector_regime(None) is None


def test_compute_market_breadth():
    assert compute_market_breadth(60, 40) == 0.6
    assert compute_market_breadth(0, 0) is None


def test_build_context_features_shape():
    stock = _returns(300)
    nifty = _returns(300, seed=7)
    sector = _returns(300, seed=13)
    result = build_context_features(
        stock_returns=stock,
        nifty_returns=nifty,
        sector_returns=sector,
        advancing=60,
        declining=40,
    )
    assert result["decision_eligibility_asserted"] is False
    for key in (
        "beta_vs_nifty",
        "beta_vs_sector_index",
        "correlation_vs_nifty",
        "correlation_vs_sector_index",
        "relative_strength_vs_nifty",
        "relative_strength_vs_sector",
        "sector_regime",
        "market_breadth",
    ):
        assert key in result
    assert result["market_breadth"] == 0.6
    assert result["sector_regime"] in ("OUTPERFORMING", "UNDERPERFORMING", "NEUTRAL")


def test_settings_defaults():
    settings = ContextSettings()
    assert settings.trailing_window == 252
    assert settings.min_observations == 30
