"""Actual Bronze-to-Silver integration and adversarial boundaries for gate results."""

from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform import legacy_gate_results as codec
from nse_quant.data_platform import legacy_gate_results_bronze as bronze
from nse_quant.data_platform import legacy_gate_results_silver_store as silver
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore

AT = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
IMPORT_AT = datetime(2026, 1, 2, tzinfo=UTC)
REVISION = "a" * 40


def seed(path):
    legacy = DuckDBStore(path=path)
    try:
        legacy.write_feature_gate_result(
            gate_result_id="A",
            ts=AT,
            run_id="R",
            symbol="NIFTY",
            passed=False,
            reasons=["replacement"],
            checks={"replacement": False},
        )
        legacy.write_feature_availability_result(
            gate_result_id="B",
            ts=AT,
            run_id="R",
            symbol="NIFTY",
            passed=True,
            reasons=["retained"],
            checks={"eligible": True},
        )
        table = bronze.common.name(legacy.conn, "main", codec.TABLE)
        legacy.conn.execute(
            f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?,CAST(? AS JSON))",
            ["C", None, None, None, None, None, None, "not-json reason", '{"x":1,"x":2}'],
        )
        legacy.conn.execute(
            f"INSERT INTO {table} SELECT 'D',ts,run_id,proposal_id,strategy,"
            f"gate,passed,reason,details FROM {table} WHERE gate_result_id='A'"
        )
    finally:
        legacy.close()


def persist(tmp_path):
    legacy, bronze_path, silver_path = (
        tmp_path / "legacy.duckdb",
        tmp_path / "bronze.duckdb",
        tmp_path / "silver.duckdb",
    )
    seed(legacy)
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(bronze_path)) as b,
        duckdb.connect(str(silver_path)) as s,
    ):
        AuditLedger(b).initialize()
        BronzeEventStore(b).initialize()
        snapshot = bronze.capture_gate_results(source, source_label="fixture")
        recorded = bronze.preserve_gate_results(
            source,
            b,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=IMPORT_AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
        silver.initialize_gate_results_silver(s)
        pins = silver.GateResultsBronzePins(
            source_label=recorded["source_label"],
            snapshot_id=recorded["snapshot_id"],
            capture_event_id=recorded["capture_event_id"],
            envelope_hash=recorded["envelope_hash"],
            recording_fingerprint=recorded["recording_fingerprint"],
        )
    with (
        duckdb.connect(str(bronze_path), read_only=True) as b,
        duckdb.connect(str(silver_path)) as s,
    ):
        context = silver.observe_gate_results_bronze(b, pins=pins)
        persisted = silver.persist_gate_results_silver(
            b,
            s,
            pins=pins,
            expected_context_sha256=codec.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return legacy, bronze_path, silver_path, recorded, persisted


def args(persisted):
    return dict(
        revision_id=persisted["revision_id"],
        expected_recording_fingerprint=persisted["recording_fingerprint"],
    )


def test_complete_source_linked_silver_preserves_every_field(tmp_path):
    legacy, bronze_path, silver_path, recorded, persisted = persist(tmp_path)
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(bronze_path), read_only=True) as b,
        duckdb.connect(str(silver_path), read_only=True) as s,
    ):
        records = silver.read_gate_results_silver(s, **args(persisted))
        assert len(records) == persisted["row_count"] == 4
        assert (
            silver.revalidate_gate_results_silver_source(source, b, s, **args(persisted)) == records
        )
        table = bronze.common.name(source, "main", codec.TABLE)
        originals = source.execute(
            f"SELECT gate_result_id,ts,run_id,proposal_id,strategy,gate,"
            f"passed,reason,CAST(details AS VARCHAR) FROM {table}"
        ).fetchall()
        by_id = {row[0]: row for row in originals}
        for ordinal, raw in enumerate(records):
            doc = codec.parse(raw, codec.MAX_RECORD)
            fields = doc["stored_fields"]
            assert doc["source_ordinal"] == ordinal
            assert fields["gate_result_id"] in by_id
            assert fields["passed"] in (True, False, None)
            assert not doc["native_decision_replayed"]
            assert not doc["decision_eligibility_asserted"]
        assert by_id["A"][6] is False
        assert by_id["B"][6] is True
        assert by_id["C"][1] is None and by_id["C"][6] is None
        assert by_id["C"][8] == '{"x":1,"x":2}'
        assert by_id["D"][0] == "D"


def test_distinct_null_boolean_and_json_text_survive(tmp_path):
    _legacy, _bronze_path, silver_path, _recorded, persisted = persist(tmp_path)
    with duckdb.connect(str(silver_path), read_only=True) as s:
        observations = silver.common.name(s, "silver", "gate_results_observations")
        rows = s.execute(
            f"SELECT gate_result_id,ts,passed,reason,details FROM {observations} "
            "ORDER BY gate_result_id"
        ).fetchall()
    by_id = {row[0]: row for row in rows}
    assert by_id["C"][1:] == (None, None, "not-json reason", '{"x":1,"x":2}')
    assert by_id["A"][2] is False
    assert by_id["B"][2] is True


def test_duplicate_retained_id_and_ordinal_uniqueness(tmp_path):
    _legacy, _bronze_path, silver_path, _recorded, persisted = persist(tmp_path)
    with duckdb.connect(str(silver_path)) as s:
        observations = silver.common.name(s, "silver", "gate_results_observations")
        with pytest.raises(duckdb.ConstraintException):
            s.execute(
                f"INSERT INTO {observations} SELECT revision_id,ordinal,record_id,"
                "gate_result_id,ts,run_id,proposal_id,strategy,gate,passed,reason,details,"
                "record_bytes,source_observation_id,recorded_at "
                f"FROM {observations} WHERE ordinal=0"
            )


def test_bronze_drift_blocks_revalidation(tmp_path):
    legacy, bronze_path, silver_path, _recorded, persisted = persist(tmp_path)
    with duckdb.connect(str(bronze_path)) as b:
        variants = bronze.common.name(b, "bronze", "event_variants")
        b.execute(f"UPDATE {variants} SET payload='bad'::BLOB")
    with (
        duckdb.connect(str(bronze_path), read_only=True) as b,
        duckdb.connect(str(silver_path), read_only=True) as s,
        pytest.raises(ValueError),
    ):
        silver.revalidate_gate_results_silver(b, s, **args(persisted))


def test_current_legacy_source_drift_is_distinct_from_retained_silver(tmp_path):
    legacy, bronze_path, silver_path, _recorded, persisted = persist(tmp_path)
    with duckdb.connect(str(legacy)) as c:
        table = bronze.common.name(c, "main", codec.TABLE)
        c.execute(f"UPDATE {table} SET passed=NOT passed")
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(bronze_path), read_only=True) as b,
        duckdb.connect(str(silver_path), read_only=True) as s,
        pytest.raises(ValueError, match="CURRENT"),
    ):
        silver.revalidate_gate_results_silver_source(source, b, s, **args(persisted))


def test_first_write_and_orphan_obligation(tmp_path):
    legacy, bronze_path, silver_path, recorded, persisted = persist(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as b,
        duckdb.connect(str(silver_path)) as s,
        pytest.raises(ValueError, match="FIRST_WRITE"),
    ):
        silver.persist_gate_results_silver(
            b,
            s,
            pins=silver.GateResultsBronzePins(
                source_label=recorded["source_label"],
                snapshot_id=recorded["snapshot_id"],
                capture_event_id=recorded["capture_event_id"],
                envelope_hash=recorded["envelope_hash"],
                recording_fingerprint=recorded["recording_fingerprint"],
            ),
            expected_context_sha256="0" * 64,
            actor_id="other",
            code_revision="b" * 40,
        )


def test_failed_extra_scoped_job_blocks_reader(tmp_path):
    _legacy, _bronze_path, silver_path, _recorded, persisted = persist(tmp_path)
    with duckdb.connect(str(silver_path)) as s:
        sets = silver.common.name(s, "silver", "gate_results_sets")
        scope = s.execute(
            f"SELECT scope_id FROM {sets} WHERE revision_id=?",
            [persisted["revision_id"]],
        ).fetchone()
        assert scope is not None and scope[0] is not None
        ledger = AuditLedger(s)
        job = ledger.plan_job(
            command_name=silver.COMMAND,
            actor_id="synthetic",
            code_revision=REVISION,
            scope_ref="sha256:" + scope[0],
            config_hash="b" * 64,
        )
        ledger.transition(job, JobState.FAILED, "EXECUTION_ERROR")
    with (
        duckdb.connect(str(silver_path), read_only=True) as s,
        pytest.raises(ValueError),
    ):
        silver.read_gate_results_silver(s, **args(persisted))
