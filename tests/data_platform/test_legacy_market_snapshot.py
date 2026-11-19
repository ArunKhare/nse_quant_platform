"""Actual disposable DuckDB capture/codec tests; no native dependency substitutes."""

import json
from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform import legacy_market_snapshot as service


@pytest.fixture
def legacy(tmp_path):
    path = tmp_path / "legacy.duckdb"
    conn = duckdb.connect(str(path))
    for table, columns in service.SCHEMAS.items():
        fields = ",".join('"' + n + '" ' + t for n, t in columns)
        conn.execute(f'CREATE TABLE "{table}" ({fields})')
    at = datetime(2026, 1, 1, tzinfo=UTC)
    candle = (257, "SYNTHETIC", "1m", at, -0.0, 2.0, 0.0, 1.0, 0, None)
    option = (
        "run",
        at,
        "LABEL",
        None,
        100.0,
        "CE",
        "LABEL",
        258,
        1,
        100.0,
        1.0,
        None,
        None,
        None,
        0,
        0.2,
        0.5,
        0.01,
        1.0,
        -0.1,
        "legacy",
        '{"x": 1}',
    )
    conn.execute("INSERT INTO spot_candles VALUES (" + ",".join("?" for _ in candle) + ")", candle)
    conn.execute("INSERT INTO option_stream VALUES (" + ",".join("?" for _ in option) + ")", option)
    conn.close()
    yield path


def capture(path, table="spot_candles"):
    with duckdb.connect(str(path), read_only=True) as conn:
        return service.capture_legacy_table(conn, table=table, source_label="fixture")


@pytest.mark.parametrize("table", ["spot_candles", "option_stream"])
def test_actual_sql_capture_roundtrip(legacy, table):
    value = capture(legacy, table)
    assert value.row_count == 1
    assert capture(legacy, table) == value
    decoded = service.replay_legacy_snapshot(value.payload, expected_snapshot_id=value.snapshot_id)
    assert decoded["table"] == table
    observations = service.typed_legacy_observations(
        value.payload, expected_snapshot_id=value.snapshot_id
    )
    assert observations[0]["decision_eligibility_asserted"] is False
    assert observations[0]["original_provider_bytes_retained"] is False
    if table == "spot_candles":
        fields = observations[0]["stored_fields"]
        assert fields["open"] == (-0.0).hex()
        assert fields["oi"] is None and fields["volume"] == "0"
    else:
        assert observations[0]["legacy_derived_fields"]["iv"] == (0.2).hex()
        assert observations[0]["stored_fields"]["payload_json"] == '{"x": 1}'


def test_timezone_does_not_change_snapshot(legacy):
    with duckdb.connect(str(legacy), read_only=True) as conn:
        first = service.capture_legacy_table(conn, table="spot_candles", source_label="fixture")
        conn.execute("SET TimeZone='Asia/Kolkata'")
        second = service.capture_legacy_table(conn, table="spot_candles", source_label="fixture")
        assert second == first


def test_writable_source_refused(legacy):
    with duckdb.connect(str(legacy)) as conn, pytest.raises(ValueError, match="READONLY"):
        service.capture_legacy_table(conn, table="spot_candles", source_label="fixture")


@pytest.mark.parametrize("table", ["unknown", 'spot_candles"; DROP TABLE x;--'])
def test_table_not_interpolated_before_validation(legacy, table):
    with pytest.raises(ValueError, match="SUPPORTED_TABLE"):
        capture(legacy, table)


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("DELETE FROM spot_candles", "ROW_BOUND"),
        ("INSERT INTO spot_candles SELECT * FROM spot_candles", "DUPLICATE"),
        ("UPDATE spot_candles SET ts=NULL", "KEY_UNKNOWN"),
        ("UPDATE spot_candles SET close='NaN'::DOUBLE", "FINITE"),
        ("ALTER TABLE spot_candles ADD COLUMN extra INTEGER", "SCHEMA"),
        ("UPDATE spot_candles SET symbol=repeat('x',65537)", "CELL_BOUND"),
    ],
)
def test_no_partial_salvage(legacy, mutation, reason):
    with duckdb.connect(str(legacy)) as conn:
        conn.execute(mutation)
    with pytest.raises(ValueError, match=reason):
        capture(legacy)


def test_real_row_limit(legacy):
    with duckdb.connect(str(legacy)) as conn:
        conn.execute(
            "INSERT INTO spot_candles SELECT 1000+i,symbol,interval,ts,open,high,"
            "low,close,volume,oi FROM spot_candles,range(1000) r(i)"
        )
    with pytest.raises(ValueError, match="ROW_BOUND"):
        capture(legacy)


@pytest.mark.parametrize("change", ["eligibility", "float", "integer", "duplicate_json", "space"])
def test_rehashed_tampering(legacy, change):
    value = capture(legacy)
    doc = json.loads(value.payload)
    if change == "eligibility":
        doc["decision_eligibility_asserted"] = True
    elif change == "float":
        doc["rows"][0][4] = "nan"
    elif change == "integer":
        doc["rows"][0][0] = "01"
    raw = service.canonical(doc)
    if change == "duplicate_json":
        raw = raw.replace(b'"version":', b'"version":"bad","version":', 1)
    if change == "space":
        raw += b" "
    with pytest.raises(ValueError):
        service.replay_legacy_snapshot(raw, expected_snapshot_id=service.digest(raw))


def test_changed_source_different_pin(legacy):
    first = capture(legacy)
    with duckdb.connect(str(legacy)) as conn:
        conn.execute("UPDATE spot_candles SET close=1.5")
    assert capture(legacy).snapshot_id != first.snapshot_id


def test_schema_view_rejected(legacy):
    with duckdb.connect(str(legacy)) as conn:
        conn.execute("ALTER TABLE spot_candles RENAME TO original")
        conn.execute("CREATE VIEW spot_candles AS SELECT * FROM original")
    with pytest.raises(ValueError, match="SCHEMA"):
        capture(legacy)


def test_operational_error_propagates(legacy):
    conn = duckdb.connect(str(legacy), read_only=True)
    conn.close()
    with pytest.raises(duckdb.Error):
        service.capture_legacy_table(conn, table="spot_candles", source_label="fixture")


def test_real_snapshot_byte_limit(legacy):
    with duckdb.connect(str(legacy)) as conn:
        conn.execute("UPDATE spot_candles SET symbol=repeat('x',65536)")
        conn.execute(
            "INSERT INTO spot_candles SELECT 1000+i,symbol,interval,ts,open,high,"
            "low,close,volume,oi FROM spot_candles,range(20) r(i)"
        )
    with pytest.raises(ValueError, match="BYTE_BOUND"):
        capture(legacy)


def test_missing_pin_does_not_accept_modified_bytes(legacy):
    value = capture(legacy)
    with pytest.raises(ValueError, match="PIN"):
        service.replay_legacy_snapshot(value.payload, expected_snapshot_id="0" * 64)
