"""Actual exit-events writer -> Bronze -> persisted Silver chain."""

from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.core.models import ExitEvaluation, ExitReason
from nse_quant.data_platform import legacy_exit_events_bronze as bronze_api
from nse_quant.data_platform import legacy_exit_events_silver_store as silver
from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.persistence.repositories import PositionRepository

AT = datetime(2026, 1, 1, 15, 30, tzinfo=UTC)
REVISION = "a" * 40


def seed(path):
    legacy = DuckDBStore(path=path)
    try:
        repository = PositionRepository(legacy.conn)
        repository.save_exit_evaluation(
            ExitEvaluation(
                strategy_position_id="sp-1",
                evaluated_at=AT,
                triggered_reasons=[ExitReason.IV_COLLAPSE],
                selected_reason=ExitReason.IV_COLLAPSE,
                details={"proposal_id": "prop-1", "strategy": "strat-1", "iv_rank": 0.1},
            )
        )
        repository.save_exit_evaluation(
            ExitEvaluation(
                strategy_position_id="sp-2",
                evaluated_at=AT,
                triggered_reasons=[],
                selected_reason=None,
                details={"proposal_id": "prop-1", "strategy": "strat-1"},
            )
        )
        table = bronze_api.common.name(legacy.conn, "main", bronze_api.codec.TABLE)
        legacy.conn.execute(
            f"INSERT INTO {table} VALUES (?,?,?,?,?,CAST(? AS JSON),?,CAST(? AS JSON))",
            ["exit-3", None, None, None, None, None, None, "null"],
        )
    finally:
        legacy.close()


def bronze(tmp_path):
    legacy_path, bronze_path = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy_path)
    with (
        duckdb.connect(str(legacy_path), read_only=True) as source,
        duckdb.connect(str(bronze_path)) as target,
    ):
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = bronze_api.capture_exit_events(source, source_label="fixture")
        result = bronze_api.preserve_exit_events(
            source,
            target,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver.ExitEventsBronzePins(
        source_label=result["source_label"],
        snapshot_id=result["snapshot_id"],
        capture_event_id=result["capture_event_id"],
        envelope_hash=result["envelope_hash"],
        recording_fingerprint=result["recording_fingerprint"],
    )


def chain(tmp_path):
    bronze_path, pins = bronze(tmp_path)
    silver_path = tmp_path / "exit_events_silver.duckdb"
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        silver.initialize_exit_events_silver(target)
        context = silver.observe_exit_events_bronze(bronze_conn, pins=pins)
        receipt = silver.persist_exit_events_silver(
            bronze_conn,
            target,
            pins=pins,
            expected_context_sha256=base.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver_path, pins, receipt


def test_exit_events_bronze_to_silver_chain(tmp_path):
    bronze_path, silver_path, pins, receipt = chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path), read_only=True) as reader,
    ):
        records = silver.read_exit_events_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )
        assert len(records) == receipt["row_count"] == 3
        assert records == bronze_api.read_exit_events_bronze(bronze_conn, **pins.reader_args())
        bronze_pins = pins.reader_args()
        bronze_pins.pop("expected_recording_fingerprint")
        assert records == silver.revalidate_exit_events_silver(
            bronze_conn,
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
            expected_bronze_recording_fingerprint=pins.recording_fingerprint,
            **bronze_pins,
        )
        rows = reader.execute(
            "SELECT exit_event_id,ts,strategy_position_id,proposal_id,strategy,"
            "triggered_reasons,selected_reason,details "
            "FROM silver.exit_event_observations WHERE revision_id=? ORDER BY ordinal",
            [receipt["revision_id"]],
        ).fetchall()
        evaluated = next(row for row in rows if row[6] == "iv_collapse")
        unevaluated = next(row for row in rows if row[0] and row[6] is None)
        null_json = next(row for row in rows if row[0] == "exit-3")
        assert evaluated[1] == AT and evaluated[5] == '["iv_collapse"]'
        assert unevaluated[1] == AT and unevaluated[5] == "[]"
        assert null_json[1:7] == (None,) * 6
        assert null_json[7] == "null"


def test_exit_events_silver_tampering(tmp_path):
    _b, silver_path, _pins, receipt = chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("UPDATE silver.exit_event_sets SET context='bad'::BLOB")
    with duckdb.connect(str(silver_path), read_only=True) as reader, pytest.raises(ValueError):
        silver.read_exit_events_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_exit_events_silver_first_write_obligation(tmp_path):
    bronze_path, silver_path, pins, receipt = chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        context = silver.observe_exit_events_bronze(bronze_conn, pins=pins)
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            silver.persist_exit_events_silver(
                bronze_conn,
                target,
                pins=pins,
                expected_context_sha256=base.sha(context),
                actor_id="other",
                code_revision="b" * 40,
            )


def test_exit_events_silver_same_file_alias(tmp_path):
    _bronze_path, silver_path, pins, _receipt = chain(tmp_path)
    with duckdb.connect(str(silver_path)) as target:
        alias = target.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                silver.persist_exit_events_silver(
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
