"""Actual orders writer -> Bronze -> persisted Silver chain."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import legacy_orders as codec
from nse_quant.data_platform import legacy_orders_bronze as bronze_api
from nse_quant.data_platform import legacy_orders_silver_store as silver
from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore

AT = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
FILLED_AT = datetime(2026, 1, 1, 9, 15, 5, tzinfo=UTC)
REVISION = "a" * 40
TABLE = '"main"."orders"'


def _seed(path: Path) -> None:
    writer = duckdb.connect(str(path))
    try:
        columns = ",".join(f'"{n}" {k}' for n, k in codec.SCHEMA)
        writer.execute(f'CREATE TABLE {TABLE} ({columns},PRIMARY KEY("order_id"))')
        writer.executemany(
            f"INSERT INTO {TABLE} VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    "order-1",
                    AT,
                    "run-1",
                    "prop-1",
                    "swing",
                    "paper",
                    "FILLED",
                    100.5,
                    100.5,
                    FILLED_AT,
                    None,
                    '{"qty":1}',
                ),
                (
                    "order-2",
                    AT,
                    "run-1",
                    "prop-1",
                    "swing",
                    "paper",
                    "REJECTED",
                    100.5,
                    None,
                    None,
                    "insufficient",
                    "[]",
                ),
                ("order-3", None, None, None, None, None, None, None, None, None, None, None),
                ("order-4", AT, "run-2", "prop-2", "swing", "paper", "PENDING", None, None, None, None, "null"),
            ],
        )
    finally:
        writer.close()


def _bronze(tmp_path: Path) -> tuple[Path, silver.OrdersBronzePins]:
    source_path, bronze_path = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    _seed(source_path)
    source = duckdb.connect(str(source_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = bronze_api.capture_orders(source, source_label="fixture")
        receipt = bronze_api.preserve_orders(
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
    return bronze_path, silver.OrdersBronzePins(
        source_label=receipt["source_label"],
        snapshot_id=receipt["snapshot_id"],
        capture_event_id=receipt["capture_event_id"],
        envelope_hash=receipt["envelope_hash"],
        recording_fingerprint=receipt["recording_fingerprint"],
    )


def _chain(tmp_path: Path) -> tuple[Path, Path, silver.OrdersBronzePins, dict[str, Any]]:
    bronze_path, pins = _bronze(tmp_path)
    silver_path = tmp_path / "orders_silver.duckdb"
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        silver.initialize_orders_silver(target)
        context = silver.observe_orders_bronze(bronze_conn, pins=pins)
        receipt = silver.persist_orders_silver(
            bronze_conn,
            target,
            pins=pins,
            expected_context_sha256=base.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver_path, pins, receipt


def test_orders_bronze_to_silver_chain(tmp_path: Path) -> None:
    bronze_path, silver_path, pins, receipt = _chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path), read_only=True) as reader,
    ):
        records = silver.read_orders_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )
        assert len(records) == receipt["row_count"] == 4
        assert records == bronze_api.read_orders_bronze(bronze_conn, **pins.reader_args())
        reader_pins = pins.reader_args()
        reader_pins.pop("expected_recording_fingerprint")
        assert records == silver.revalidate_orders_silver(
            bronze_conn,
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
            expected_bronze_recording_fingerprint=pins.recording_fingerprint,
            **reader_pins,
        )
        rows = reader.execute(
            "SELECT order_id,ts,run_id,proposal_id,strategy,broker,status,limit_price,"
            "filled_price,filled_at,reject_reason,payload "
            "FROM silver.order_observations WHERE revision_id=? ORDER BY ordinal",
            [receipt["revision_id"]],
        ).fetchall()
        assert rows[0][0] == "order-1" and rows[0][7] == 100.5 and rows[0][8] == 100.5
        assert rows[1][8] is None and rows[1][10] == "insufficient"
        assert rows[2][1:] == (None,) * 11
        assert rows[3][7] is None and rows[3][11] == "null"


@pytest.mark.parametrize(
    "column,value",
    [
        ("order_id", "order_id || '-changed'"),
        ("ts", "ts + INTERVAL '1 microsecond'"),
        ("run_id", "'changed'"),
        ("proposal_id", "'changed'"),
        ("strategy", "'changed'"),
        ("broker", "'changed'"),
        ("status", "'changed'"),
        ("limit_price", "limit_price + 0.5"),
        ("filled_price", "filled_price + 0.5"),
        ("filled_at", "filled_at + INTERVAL '1 microsecond'"),
        ("reject_reason", "'changed'"),
        ("payload", "'changed'"),
    ],
    ids=[
        "key",
        "instant",
        "run",
        "proposal",
        "strategy",
        "broker",
        "status",
        "limit-price",
        "filled-price",
        "filled-at",
        "reject-reason",
        "payload",
    ],
)
def test_materialized_field_corruption_rejected(tmp_path: Path, column: str, value: str) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute(f"UPDATE silver.order_observations SET {column}={value} WHERE ordinal=0")
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError, match="MATERIALIZED_FIELD_MISMATCH"),
    ):
        silver.read_orders_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_missing_row_rejected(tmp_path: Path) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("DELETE FROM silver.order_observations WHERE ordinal=0")
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError, match="ORDINAL_COVERAGE_MISMATCH"),
    ):
        silver.read_orders_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_ordinal_gap_rejected(tmp_path: Path) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("UPDATE silver.order_observations SET ordinal=ordinal+10 WHERE ordinal=1")
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError, match="ORDINAL_COVERAGE_MISMATCH"),
    ):
        silver.read_orders_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_sql_null_and_json_null_distinct(tmp_path: Path) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("UPDATE silver.order_observations SET payload=NULL WHERE ordinal=3")
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError, match="MATERIALIZED_FIELD_MISMATCH"),
    ):
        silver.read_orders_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_orders_silver_tampering(tmp_path: Path) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("UPDATE silver.order_sets SET context='bad'::BLOB")
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError),
    ):
        silver.read_orders_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_orders_silver_first_write_obligation(tmp_path: Path) -> None:
    bronze_path, silver_path, pins, receipt = _chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        context = silver.observe_orders_bronze(bronze_conn, pins=pins)
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            silver.persist_orders_silver(
                bronze_conn,
                target,
                pins=pins,
                expected_context_sha256=base.sha(context),
                actor_id="other",
                code_revision="b" * 40,
            )


def test_orders_silver_same_file_alias(tmp_path: Path) -> None:
    _bronze_path, silver_path, pins, _receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as target:
        alias = target.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                silver.persist_orders_silver(
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
