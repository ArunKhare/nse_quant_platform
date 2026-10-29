import json

from nse_quant.research.backtest_reporting import count_warehouse_days, generate_digest


def test_count_warehouse_days(tmp_path):
    warehouse = tmp_path / "exports"
    (warehouse / "underlying=NIFTY" / "year=2026" / "month=10").mkdir(parents=True)

    (
        warehouse
        / "underlying=NIFTY"
        / "year=2026"
        / "month=10"
        / "option_stream_2026-10-28.parquet"
    ).write_bytes(b"x")
    (
        warehouse
        / "underlying=NIFTY"
        / "year=2026"
        / "month=10"
        / "option_stream_2026-10-29.parquet"
    ).write_bytes(b"x")

    assert count_warehouse_days(warehouse) == 2


def test_digest_writes_json(tmp_path):
    readiness_path = tmp_path / "readiness.json"
    readiness_path.write_text(
        json.dumps({"ready": False}),
        encoding="utf-8",
    )

    registry_path = tmp_path / "experiment_index.csv"
    warehouse_dir = tmp_path / "exports"
    output_path = tmp_path / "daily_status.json"

    digest = generate_digest(
        readiness_path=readiness_path,
        registry_path=registry_path,
        warehouse_dir=warehouse_dir,
        output_path=output_path,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["readiness"] == {"ready": False}
    assert payload["warehouse_option_stream_days"] == 0
    assert payload["latest_experiment"] is None
    assert digest["generated_at"]
