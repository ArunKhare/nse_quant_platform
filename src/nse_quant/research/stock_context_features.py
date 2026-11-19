"""Stock context features; research-only calculator, no execution authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ContextSettings:
    trailing_window: int = 252
    min_observations: int = 30


def compute_beta(stock_returns: pd.Series, benchmark_returns: pd.Series, *, window: int = 252) -> float | None:
    """Beta of stock vs benchmark from aligned daily returns over a trailing window."""
    if len(stock_returns) < window or len(benchmark_returns) < window:
        return None
    aligned = pd.concat([stock_returns.tail(window), benchmark_returns.tail(window)], axis=1, join="inner").dropna()
    if len(aligned) < 2:
        return None
    cov = np.cov(aligned.iloc[:, 0], aligned.iloc[:, 1])
    var_b = cov[1, 1]
    if var_b == 0:
        return None
    return float(cov[0, 1] / var_b)


def compute_correlation(stock_returns: pd.Series, benchmark_returns: pd.Series, *, window: int = 252) -> float | None:
    """Correlation of stock vs benchmark from aligned daily returns over a trailing window."""
    if len(stock_returns) < window or len(benchmark_returns) < window:
        return None
    aligned = pd.concat([stock_returns.tail(window), benchmark_returns.tail(window)], axis=1, join="inner").dropna()
    if len(aligned) < 2:
        return None
    corr = np.corrcoef(aligned.iloc[:, 0], aligned.iloc[:, 1])
    return float(corr[0, 1])


def compute_relative_strength(
    stock_returns: pd.Series, benchmark_returns: pd.Series, *, window: int = 252
) -> float | None:
    """Relative strength: cumulative stock return minus cumulative benchmark return over the window."""
    if len(stock_returns) < window or len(benchmark_returns) < window:
        return None
    stock_cum = float((1 + stock_returns.tail(window)).prod() - 1)
    bench_cum = float((1 + benchmark_returns.tail(window)).prod() - 1)
    return stock_cum - bench_cum


def classify_sector_regime(relative_strength: float | None) -> str | None:
    """Classify sector regime from relative strength; observational only."""
    if relative_strength is None:
        return None
    if relative_strength > 0.05:
        return "OUTPERFORMING"
    if relative_strength < -0.05:
        return "UNDERPERFORMING"
    return "NEUTRAL"


def compute_market_breadth(advancing: int, declining: int) -> float | None:
    """Market breadth: advancing / (advancing + declining); None if no constituents."""
    total = advancing + declining
    if total == 0:
        return None
    return advancing / total


def build_context_features(
    *,
    stock_returns: pd.Series,
    nifty_returns: pd.Series,
    sector_returns: pd.Series,
    advancing: int,
    declining: int,
    settings: ContextSettings | None = None,
) -> dict[str, Any]:
    """Build the full stock-context feature payload; observational only."""
    settings = settings or ContextSettings()
    beta_nifty = compute_beta(stock_returns, nifty_returns, window=settings.trailing_window)
    beta_sector = compute_beta(stock_returns, sector_returns, window=settings.trailing_window)
    corr_nifty = compute_correlation(stock_returns, nifty_returns, window=settings.trailing_window)
    corr_sector = compute_correlation(stock_returns, sector_returns, window=settings.trailing_window)
    rs_nifty = compute_relative_strength(stock_returns, nifty_returns, window=settings.trailing_window)
    rs_sector = compute_relative_strength(stock_returns, sector_returns, window=settings.trailing_window)
    return {
        "beta_vs_nifty": beta_nifty,
        "beta_vs_sector_index": beta_sector,
        "correlation_vs_nifty": corr_nifty,
        "correlation_vs_sector_index": corr_sector,
        "relative_strength_vs_nifty": rs_nifty,
        "relative_strength_vs_sector": rs_sector,
        "sector_regime": classify_sector_regime(rs_sector),
        "market_breadth": compute_market_breadth(advancing, declining),
        "decision_eligibility_asserted": False,
    }
