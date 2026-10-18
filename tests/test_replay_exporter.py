import json
from nse_quant.market_data.replay_exporter import ReplayExporter
def test_replay_exporter_writes_snapshots(
    test_store,
    tmp_path,
):
    exporter = ReplayExporter(test_store)
    output = tmp_path / "replay.json"

    result = exporter.export_recent_snapshots(
        underlying="NIFTY",
        output_path=output,
        minutes=60,
    )

    assert result.exists()

    payload = json.loads(result.read_text(encoding="utf-8"))
    assert "snapshots" in payload

