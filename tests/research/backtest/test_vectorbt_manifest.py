"""Tests for deterministic vectorbt run manifests."""

from __future__ import annotations

from nse_quant.research.backtest.vectorbt_manifest import build_manifest


def test_manifest_is_deterministic():
    first = build_manifest(
        strategy="iron_condor_monitor",
        underlying="NIFTY",
        input_hash="a" * 64,
        parameters={"initial_capital": 1_000_000.0},
        result={"total_return": 0.01},
    )
    second = build_manifest(
        strategy="iron_condor_monitor",
        underlying="NIFTY",
        input_hash="a" * 64,
        parameters={"initial_capital": 1_000_000.0},
        result={"total_return": 0.01},
    )

    assert first == second
    assert first["decision_eligibility_asserted"] is False
    assert len(first["manifest_sha256"]) == 64
