import json

from scripts.research_status_digest import count_warehouse_days


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
    readiness = tmp_path / "readiness.json"
    readiness.write_text(json.dumps({"ready": False}), encoding="utf-8")

    output = tmp_path / "daily_status.json"

    # Call the digest-generation function after refactoring it out of main(),
    # or invoke the CLI with --readiness/--output pointing to tmp_path.

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["readiness"] == {"ready": False}
