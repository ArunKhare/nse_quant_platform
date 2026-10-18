from __future__ import annotations

import json

from nse_quant.market_data.replay_exporter import ReplayExporter
from nse_quant.market_data.replay_provider import (
    ReplayMarketDataProvider,
)


def test_replay_exporter_writes_snapshots(
    test_store,
    tmp_path,
    snapshot_factory,
):
    snapshot = snapshot_factory(
        spot=23000.0,
        call_price=120.0,
        put_price=115.0,
    )
    test_store.write_option_stream("replay-test", snapshot)

    exporter = ReplayExporter(test_store)
    output = tmp_path / "replay.json"

    result = exporter.export_recent_snapshots(
        underlying="NIFTY",
        output_path=output,
        minutes=60,
    )

    assert result.exists()

    payload = json.loads(
        result.read_text(encoding="utf-8")
    )

    assert "snapshots" in payload
    assert payload["snapshots"][0]["spot"] == snapshot.spot


def test_replay_provider_requires_snapshots():
    import pytest

    with pytest.raises(ValueError):
        ReplayMarketDataProvider([])
