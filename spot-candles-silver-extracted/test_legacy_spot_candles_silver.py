"""Actual spot-candles writer -> Bronze -> persisted Silver chain."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform import legacy_spot_candles as codec
from nse_quant.data_platform import legacy_spot_candles_bronze as bronze_api
from nse_quant.data_platform import legacy_spot_candles_silver_store as silver
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore

AT = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
REVISION = "a" * 40
TABLE = '"main"."spot_candles"'


def _seed(path: Path) -> None:
    writer = duckdb.connect(str(path))
    try:
        columns = ",".join(f'"{n}" {k}' for n, k in codec.SCHEMA)
        writer.execute(f'CREATE TABLE {TABLE} ({columns},PRIMARY KEY("instrument_token","interval","ts"))')
        writer.executemany(
            f"INSERT INTO {TABLE} VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                (123456, "NIFTY", "1m", AT, 100.0, 101.0, 99.0, 100.5, 1000, 500),
                (123456, "NIFTY", "1m", AT.replace(minute=16), 100.5, None, None, None, None, None),
                (123457, "BANKNIFTY", "1m", AT, None, None, None, None, None, None),
                (123457, "BANKNIFTY", "1m", AT.replace(minute=16), 50000.0, 50100.0, 49900.0, 50050.0, 2000, 800),
            ],
        )
    finally:
        writer.close()


def _bronze(tmp_path: Path) -> tuple[Path, silver.SpotCandlesBronzePins]:
    source_path, bronze_path = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    _seed(source_path)
    source = duckdb.connect(str(source_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = bronze_api.capture_spot_candles(source, source_label="fixture")
        receipt = bronze_api.preserve_spot_candles(
            source,
            target,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
    finally:
        target.close()
        source.close()
    return bronze_path, silver.SpotCandlesBronzePins(
        source_label=receipt["source_label"],
        snapshot_id=receipt["snapshot_id"],
        capture_event_id=receipt["capture_event_id"],
        envelope_hash=receipt["envelope_hash"],
        recording_fingerprint=receipt["recording_fingerprint"],
    )


def _chain(tmp_path: Path) -> tuple[Path, Path, silver.SpotCandlesBronzePins, dict[str, Any]]:
    bronze_path, pins = _bronze(tmp_path)
    silver_path = tmp_path / "spot_candles_silver.duckdb"
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        silver.initialize_spot_candles_silver(target)
        context = silver.observe_spot_candles_bronze(bronze_conn, pins=pins)
        receipt = silver.persist_spot_candles_silver(
            bronze_conn,
            target,
            pins=pins,
            expected_context_sha256=base.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver_path, pins, receipt


def test_spot_candles_bronze_to_silver_chain(tmp_path: Path) -> None:
    bronze_path, silver_path, pins, receipt = _chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path), read_only=True) as reader,
    ):
        records = silver.read_spot_candles_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )
        assert len(records) == receipt["row_count"] == 4
        assert records == bronze_api.read_spot_candles_bronze(bronze_conn, **pins.reader_args())
        reader_pins = pins.reader_args()
        reader_pins.pop("expected_recording_fingerprint")
        assert records == silver.revalidate_spot_candles_silver(
            bronze_conn,
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
            expected_bronze_recording_fingerprint=pins.recording_fingerprint,
            **reader_pins,
        )
        rows = reader.execute(
            "SELECT instrument_token,symbol,interval,ts,open,high,low,close,volume,oi "
            "FROM silver.spot_candle_observations WHERE revision_id=? ORDER BY ordinal",
            [receipt["revision_id"]],
        ).fetchall()
        by_key = {(row[0], row[2], row[3]): row for row in rows}
        assert by_key[(123456, "1m", AT)][4] == 100.0 and by_key[(123456, "1m", AT)][9] == 500
        assert by_key[(123456, "1m", AT.replace(minute=16))][4:] == (100.5, None, None, None, None, None)
        assert by_key[(123457, "1m", AT)][4:] == (None,) * 6
        assert by_key[(123457, "1m", AT.replace(minute=16))][7] == 50050.0


@pytest.mark.parametrize(
    "column,value",
    [
        ("instrument_token", "instrument_token + 1"),
        ("symbol", "'changed'"),
        ("interval", "'changed'"),
        ("ts", "ts + INTERVAL '1 microsecond'"),
        ("open", "open + 0.5"),
        ("high", "high + 0.5"),
        ("low", "low + 0.5"),
        ("close", "close + 0.5"),
        ("volume", "volume + 1"),
        ("oi", "oi + 1"),
    ],
    ids=[
        "instrument-token",
        "symbol",
        "interval",
        "ts",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "oi",
    ],
)
def test_materialized_field_corruption_rejected(tmp_path: Path, column: str, value: str) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        changed = writer.execute(
            f"UPDATE silver.spot_candle_observations SET {column}={value} WHERE ordinal=0 RETURNING 1"
        ).fetchone()
        assert changed == (1,)
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError, match="MATERIALIZED_FIELD_MISMATCH"),
    ):
        silver.read_spot_candles_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_missing_row_rejected(tmp_path: Path) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("DELETE FROM silver.spot_candle_observations WHERE ordinal=0")
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError, match="ORDINAL_COVERAGE_MISMATCH"),
    ):
        silver.read_spot_candles_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_ordinal_gap_rejected(tmp_path: Path) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("UPDATE silver.spot_candle_observations SET ordinal=ordinal+10 WHERE ordinal=1")
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError, match="ORDINAL_COVERAGE_MISMATCH"),
    ):
        silver.read_spot_candles_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_spot_candles_silver_tampering(tmp_path: Path) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("UPDATE silver.spot_candle_sets SET context='bad'::BLOB")
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError),
    ):
        silver.read_spot_candles_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_spot_candles_silver_first_write_obligation(tmp_path: Path) -> None:
    bronze_path, silver_path, pins, receipt = _chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        context = silver.observe_spot_candles_bronze(bronze_conn, pins=pins)
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            silver.persist_spot_candles_silver(
                bronze_conn,
                target,
                pins=pins,
                expected_context_sha256=base.sha(context),
                actor_id="other",
                code_revision="b" * 40,
            )


def test_spot_candles_silver_same_file_alias(tmp_path: Path) -> None:
    _bronze_path, silver_path, pins, _receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as target:
        alias = target.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                silver.persist_spot_candles_silver(
                    alias,
                    target,
                    pins=pins,
                    expected_context_sha256="a" * 64,
                    actor_id="synthetic",
                    code_revision=REVISION,
                )
            assert target.execute("SELECT 1").fetchone() == (1,)
        finally:
            alias.close()
