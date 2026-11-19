"""Actual daily-RV writer -> Bronze -> persisted materialized Silver chain."""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import legacy_daily_rv_observations as codec
from nse_quant.data_platform import legacy_daily_rv_observations_bronze as bronze_api
from nse_quant.data_platform import legacy_daily_rv_observations_silver_store as silver
from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore

AT = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
DAY = date(2026, 1, 1)
REVISION = "a" * 40
TABLE = '"main"."daily_rv_observations"'


def _seed(path: Path) -> None:
    writer = duckdb.connect(str(path))
    try:
        columns = ",".join(f'"{n}" {k}' for n, k in codec.SCHEMA)
        writer.execute(f'CREATE TABLE {TABLE} ({columns},PRIMARY KEY("symbol","trading_date"))')
        writer.executemany(
            f"INSERT INTO {TABLE} VALUES (?,?,?,?)",
            [
                ("NIFTY", DAY, 0.01, 375),
                ("BANKNIFTY", DAY, 0.02, 375),
                ("NIFTY", date(2026, 1, 2), 0.015, 374),
            ],
        )
    finally:
        writer.close()


def _bronze(tmp_path: Path) -> tuple[Path, silver.DailyRVBronzePins]:
    source_path, bronze_path = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    _seed(source_path)
    source = duckdb.connect(str(source_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = bronze_api.capture_daily_rv_observations(source, source_label="fixture")
        receipt = bronze_api.preserve_daily_rv_observations(
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
    return bronze_path, silver.DailyRVBronzePins(
        source_label=receipt["source_label"],
        snapshot_id=receipt["snapshot_id"],
        capture_event_id=receipt["capture_event_id"],
        envelope_hash=receipt["envelope_hash"],
        recording_fingerprint=receipt["recording_fingerprint"],
    )


def _chain(tmp_path: Path) -> tuple[Path, Path, silver.DailyRVBronzePins, dict[str, Any]]:
    bronze_path, pins = _bronze(tmp_path)
    silver_path = tmp_path / "daily_rv_silver.duckdb"
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        silver.initialize_daily_rv_silver(target)
        context = silver.observe_daily_rv_bronze(bronze_conn, pins=pins)
        receipt = silver.persist_daily_rv_silver(
            bronze_conn,
            target,
            pins=pins,
            expected_context_sha256=base.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver_path, pins, receipt


def test_daily_rv_bronze_to_silver_chain(tmp_path: Path) -> None:
    bronze_path, silver_path, pins, receipt = _chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path), read_only=True) as reader,
    ):
        records = silver.read_daily_rv_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )
        assert len(records) == receipt["row_count"] == 3
        assert records == bronze_api.read_daily_rv_observations_bronze(bronze_conn, **pins.reader_args())
        reader_pins = pins.reader_args()
        reader_pins.pop("expected_recording_fingerprint")
        assert records == silver.revalidate_daily_rv_silver(
            bronze_conn,
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
            expected_bronze_recording_fingerprint=pins.recording_fingerprint,
            **reader_pins,
        )
        rows = reader.execute(
            "SELECT symbol,trading_date,rv,observation_count "
            "FROM silver.daily_rv_materialized_observations WHERE revision_id=? ORDER BY ordinal",
            [receipt["revision_id"]],
        ).fetchall()
        by_key = {(row[0], row[1]): row for row in rows}
        assert by_key[("NIFTY", DAY)] == ("NIFTY", DAY, 0.01, 375)
        assert by_key[("BANKNIFTY", DAY)] == ("BANKNIFTY", DAY, 0.02, 375)
        assert by_key[("NIFTY", date(2026, 1, 2))] == (
            "NIFTY",
            date(2026, 1, 2),
            0.015,
            374,
        )


@pytest.mark.parametrize(
    "column,value",
    [
        ("symbol", "'changed'"),
        ("trading_date", "DATE '2026-02-01'"),
        ("rv", "1.0"),
        ("observation_count", "999"),
    ],
    ids=["symbol", "trading-date", "rv", "observation-count"],
)
def test_materialized_field_corruption_rejected(tmp_path: Path, column: str, value: str) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        changed = writer.execute(
            f"UPDATE silver.daily_rv_materialized_observations SET {column}={value} WHERE ordinal=0 RETURNING 1"
        ).fetchone()
        assert changed == (1,)
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError, match="MATERIALIZED_FIELD_MISMATCH"),
    ):
        silver.read_daily_rv_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_missing_row_rejected(tmp_path: Path) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("DELETE FROM silver.daily_rv_materialized_observations WHERE ordinal=0")
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError, match="ORDINAL_COVERAGE_MISMATCH"),
    ):
        silver.read_daily_rv_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_ordinal_gap_rejected(tmp_path: Path) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("UPDATE silver.daily_rv_materialized_observations SET ordinal=ordinal+10 WHERE ordinal=1")
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError, match="ORDINAL_COVERAGE_MISMATCH"),
    ):
        silver.read_daily_rv_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_daily_rv_silver_tampering(tmp_path: Path) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("UPDATE silver.daily_rv_materialized_sets SET context='bad'::BLOB")
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError),
    ):
        silver.read_daily_rv_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_daily_rv_silver_first_write_obligation(tmp_path: Path) -> None:
    bronze_path, silver_path, pins, receipt = _chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        context = silver.observe_daily_rv_bronze(bronze_conn, pins=pins)
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            silver.persist_daily_rv_silver(
                bronze_conn,
                target,
                pins=pins,
                expected_context_sha256=base.sha(context),
                actor_id="other",
                code_revision="b" * 40,
            )


def test_daily_rv_silver_same_file_alias(tmp_path: Path) -> None:
    _bronze_path, silver_path, pins, _receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as target:
        alias = target.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                silver.persist_daily_rv_silver(
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
