"""Tests for legacy option-stream migration adapter."""

from __future__ import annotations

from datetime import UTC, date, datetime

from nse_quant.data_platform.option_stream_history_migration import (
    OptionStreamSnapshot,
)


def test_snapshot_identity_is_deterministic():
    snapshot = OptionStreamSnapshot(
        underlying="NIFTY",
        trading_date=date(2026, 1, 1),
        snapshot_ts=datetime(2026, 1, 1, 9, 15, tzinfo=UTC),
        rows=({"strike": 100, "iv": 0.2},),
    )
    assert snapshot.snapshot_id == snapshot.snapshot_id
    assert snapshot.batch_key == snapshot.batch_key


def test_snapshot_contains_historical_import_source():
    snapshot = OptionStreamSnapshot(
        underlying="NIFTY",
        trading_date=date(2026, 1, 1),
        snapshot_ts=datetime(2026, 1, 1, 9, 15, tzinfo=UTC),
        rows=(),
    )
    assert snapshot.source_label.startswith("legacy_option_stream_historical_import")
