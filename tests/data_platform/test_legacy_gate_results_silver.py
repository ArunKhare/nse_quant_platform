"""Actual gate-results writer -> Bronze -> persisted Silver chain."""

from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform import legacy_gate_results_bronze as bronze_api
from nse_quant.data_platform import legacy_gate_results_silver_store as silver
from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore

AT = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
REVISION = "a" * 40


def seed(path):
    legacy = DuckDBStore(path=path)
    try:
        legacy.write_feature_gate_result(
            gate_result_id="gate-1",
            ts=AT,
            run_id="run-1",
            symbol="NIFTY",
            passed=True,
            reasons=["ok"],
            checks={"iv_rank": True},
        )
        legacy.write_feature_gate_result(
            gate_result_id="gate-2",
            ts=AT,
            run_id="run-1",
            symbol="NIFTY",
            passed=False,
            reasons=[],
            checks={"iv_rank": False},
        )
        legacy.write_feature_availability_result(
            gate_result_id="gate-3",
            ts=None,
            run_id=None,
            symbol=None,
            passed=None,
            reasons=None,
            checks=None,
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
        snapshot = bronze_api.capture_gate_results(source, source_label="fixture")
        result = bronze_api.preserve_gate_results(
            source,
            target,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver.GateResultsBronzePins(
        source_label=result["source_label"],
        snapshot_id=result["snapshot_id"],
        capture_event_id=result["capture_event_id"],
        envelope_hash=result["envelope_hash"],
        recording_fingerprint=result["recording_fingerprint"],
    )


def chain(tmp_path):
    bronze_path, pins = bronze(tmp_path)
    silver_path = tmp_path / "gate_results_silver.duckdb"
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        silver.initialize_gate_results_silver(target)
        context = silver.observe_gate_results_bronze(bronze_conn, pins=pins)
        receipt = silver.persist_gate_results_silver(
            bronze_conn,
            target,
            pins=pins,
            expected_context_sha256=base.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver_path, pins, receipt


def test_gate_results_bronze_to_silver_chain(tmp_path):
    bronze_path, silver_path, pins, receipt = chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path), read_only=True) as reader,
    ):
        records = silver.read_gate_results_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )
        assert len(records) == receipt["row_count"] == 3
        assert records == bronze_api.read_gate_results_bronze(bronze_conn, **pins.reader_args())
        reader_pins = pins.reader_args()
        reader_pins.pop("expected_recording_fingerprint")
        assert records == silver.revalidate_gate_results_silver(
            bronze_conn,
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
            expected_bronze_recording_fingerprint=pins.recording_fingerprint,
            **reader_pins,
        )
        rows = reader.execute(
            "SELECT gate_result_id,ts,run_id,proposal_id,strategy,gate,passed,reason,details "
            "FROM silver.gate_result_observations WHERE revision_id=? ORDER BY ordinal",
            [receipt["revision_id"]],
        ).fetchall()
        assert rows[0][0] == "gate-1" and rows[0][6] is True
        assert rows[1][6] is False and rows[1][7] == "[]"
        assert rows[1][8] == '{"iv_rank": false}'
        assert rows[2][1:] == (
            None,
            None,
            None,
            "feature_availability",
            "feature_availability",
            None,
            "null",
            "null",
        )


def test_gate_results_silver_tampering(tmp_path):
    _b, silver_path, _pins, receipt = chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("UPDATE silver.gate_result_sets SET context='bad'::BLOB")
    with duckdb.connect(str(silver_path), read_only=True) as reader, pytest.raises(ValueError):
        silver.read_gate_results_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_gate_results_silver_first_write_obligation(tmp_path):
    bronze_path, silver_path, pins, receipt = chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        context = silver.observe_gate_results_bronze(bronze_conn, pins=pins)
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            silver.persist_gate_results_silver(
                bronze_conn,
                target,
                pins=pins,
                expected_context_sha256=base.sha(context),
                actor_id="other",
                code_revision="b" * 40,
            )


def test_gate_results_silver_same_file_alias(tmp_path):
    _bronze_path, silver_path, pins, _receipt = chain(tmp_path)
    with duckdb.connect(str(silver_path)) as target:
        alias = target.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                silver.persist_gate_results_silver(
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
