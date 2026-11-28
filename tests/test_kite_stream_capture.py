from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from nse_quant.market_data.kite_stream import _stamp_snapshot_batch


def test_snapshot_batch_uses_one_timestamp_for_all_expiries() -> None:
    snapshots = [SimpleNamespace(ts=None), SimpleNamespace(ts=None)]
    captured_at = datetime(2026, 11, 28, 6, 0, tzinfo=UTC)

    _stamp_snapshot_batch(snapshots, captured_at)

    assert [snapshot.ts for snapshot in snapshots] == [captured_at, captured_at]


def test_snapshot_batch_timestamp_advances_between_capture_cycles() -> None:
    snapshots = [SimpleNamespace(ts=None), SimpleNamespace(ts=None)]
    first_capture = datetime(2026, 11, 28, 6, 0, tzinfo=UTC)
    second_capture = datetime(2026, 11, 28, 6, 0, 1, tzinfo=UTC)

    _stamp_snapshot_batch(snapshots, first_capture)
    _stamp_snapshot_batch(snapshots, second_capture)

    assert [snapshot.ts for snapshot in snapshots] == [second_capture, second_capture]
