"""Parity tests for canonical primitives and research IV surface."""

from __future__ import annotations

import pandas as pd

from nse_quant.core.calculations import time_to_expiry_years
from nse_quant.research.iv_surface import build_single_expiry_iv_report


def test_single_expiry_report_requires_explicit_rate():
    frame = pd.DataFrame(
        {
            "ts": [pd.Timestamp("2026-01-01", tz="UTC")],
            "underlying": ["NIFTY"],
            "expiry": [pd.Timestamp("2026-01-30").date()],
            "strike": [100],
            "option_type": ["CE"],
            "ltp": [10],
            "spot": [100],
            "iv": [0.25],
            "delta": [None],
        }
    )
    report = build_single_expiry_iv_report(
        frame,
        underlying="NIFTY",
        risk_free_rate=0.07,
    )
    assert not report.empty


def test_canonical_time_to_expiry_positive():
    as_of = pd.Timestamp("2026-01-01", tz="UTC").to_pydatetime()
    expiry = pd.Timestamp("2026-01-30", tz="UTC").to_pydatetime()
    assert time_to_expiry_years(as_of=as_of, expiry=expiry) > 0
