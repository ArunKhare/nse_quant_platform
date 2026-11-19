"""Parity tests for canonical primitives and live feature assembly."""

from __future__ import annotations

from nse_quant.analytics.features import iv_percentile, iv_rank, realized_volatility
from nse_quant.core.calculations import (
    iv_percentile as canonical_iv_percentile,
)
from nse_quant.core.calculations import (
    iv_rank as canonical_iv_rank,
)
from nse_quant.core.calculations import (
    realized_volatility as canonical_realized_volatility,
)


def test_iv_rank_parity():
    assert iv_rank(20, [10, 20, 30]) == canonical_iv_rank(20, [10, 20, 30])


def test_iv_percentile_parity():
    assert iv_percentile(20, [10, 20, 30]) == canonical_iv_percentile(20, [10, 20, 30])


def test_realized_volatility_parity():
    closes = [100 + i for i in range(30)]
    assert realized_volatility(closes, window=20) == canonical_realized_volatility(closes, window=20)
