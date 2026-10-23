"""Classify daily IV regimes from IV surface research data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def classify_iv_regimes(
    daily_report: pd.DataFrame,
    *,
    iv_low_percentile: float = 0.30,
    iv_high_percentile: float = 0.70,
) -> pd.DataFrame:
    """Add IV-level, term-structure, and skew regime labels."""
    if daily_report.empty:
        return pd.DataFrame()

    frame = daily_report.copy().sort_values("trade_date")

    required = {
        "trade_date",
        "underlying",
        "median_atm_iv_near",
        "median_term_structure",
        "median_put_call_skew",
    }

    missing = required.difference(frame.columns)

    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    low_threshold = frame["median_atm_iv_near"].quantile(iv_low_percentile)

    high_threshold = frame["median_atm_iv_near"].quantile(iv_high_percentile)

    def iv_level(value: float) -> str:
        if value <= low_threshold:
            return "LOW_IV"
        if value >= high_threshold:
            return "HIGH_IV"
        return "NORMAL_IV"

    def term_structure(value: float) -> str:
        if value > 0.25:
            return "CONTANGO"
        if value < -0.25:
            return "BACKWARDATION"
        return "FLAT_TERM"

    def skew_regime(value: float) -> str:
        if value > 1.0:
            return "HIGH_PUT_SKEW"
        if value < -0.5:
            return "CALL_SKEW"
        return "NORMAL_SKEW"

    frame["iv_level"] = frame["median_atm_iv_near"].apply(iv_level)

    frame["iv_term_regime"] = frame["median_term_structure"].apply(term_structure)

    frame["iv_skew_regime"] = frame["median_put_call_skew"].apply(skew_regime)

    frame["iv_regime"] = (
        frame["iv_level"] + "_" + frame["iv_term_regime"] + "_" + frame["iv_skew_regime"]
    )

    return frame


def save_regime_report(
    report: pd.DataFrame,
    *,
    output_dir: str | Path,
    underlying: str,
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    output = output_path / f"iv_regimes_{underlying}.csv"

    report.to_csv(output, index=False)
    return output
