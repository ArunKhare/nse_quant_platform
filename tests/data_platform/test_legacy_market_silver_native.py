"""Actual disposable legacy -> Bronze -> persisted Silver; no successful substitutes.

Repository QA required. Sandbox execution does not supply native dependency replicas.
"""

import json
from datetime import UTC, datetime

import duckdb
import pytest
from test_legacy_market_snapshot import capture
from test_legacy_market_snapshot import legacy as legacy
from test_legacy_market_snapshot_native import run as preserve
from test_legacy_market_snapshot_native import target

from nse_quant.data_platform import legacy_market_silver as codec
from nse_quant.data_platform import legacy_market_silver_store as service
from nse_quant.data_platform.audit import AuditLedger, JobState

bronze_target = target


@pytest.fixture
def pipeline(legacy, bronze_target, tmp_path):
    result = preserve(legacy, bronze_target)
    pins = codec.LegacyBronzePins(
        result["capture_event_id"], result["envelope_hash"], result["snapshot_id"]
    )
    silver = tmp_path / "silver.duckdb"
    with duckdb.connect(str(silver)) as target:
        service.initialize_legacy_silver(target)
    with duckdb.connect(str(bronze_target), read_only=True) as bronze:
        context = service.observe_legacy_bronze(bronze, pins=pins)
    return bronze_target, silver, pins, context


def build(pipeline, **changes):
    bronze_path, silver_path, pins, context = pipeline
    args = dict(
        pins=pins,
        expected_source_context_sha256=codec.sha(context),
        actor_id="synthetic",
        code_revision="a" * 40,
    )
    args.update(changes)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze,
        duckdb.connect(str(silver_path)) as silver,
    ):
        return service.persist_legacy_silver(bronze, silver, **args)


def read(pipeline, result, *, current=False):
    bronze_path, silver_path, _pins, _context = pipeline
    args = dict(
        revision_id=result["revision_id"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    with duckdb.connect(str(silver_path), read_only=True) as silver:
        if current:
            with duckdb.connect(str(bronze_path), read_only=True) as bronze:
                return service.revalidate_legacy_silver(bronze, silver, **args)
        return service.read_legacy_silver(silver, **args)


def test_actual_pipeline_exact_reconciliation(pipeline):
    result = build(pipeline)
    rows = read(pipeline, result, current=True)
    assert len(rows) == result["row_count"] == 1
    body = json.loads(rows[0])
    assert body["stored_fields"]["oi"] is None
    assert body["stored_fields"]["volume"] == "0"
    assert body["stored_fields"]["open"] == (-0.0).hex()
    assert body["decision_eligibility_asserted"] is False


def test_option_analytics_not_recomputed(legacy, bronze_target, tmp_path):
    snapshot = capture(legacy, "option_stream")
    original = preserve(
        legacy, bronze_target, table="option_stream", expected_snapshot_id=snapshot.snapshot_id
    )
    pins = codec.LegacyBronzePins(
        original["capture_event_id"], original["envelope_hash"], original["snapshot_id"]
    )
    silver_path = tmp_path / "options.duckdb"
    with (
        duckdb.connect(str(bronze_target), read_only=True) as bronze,
        duckdb.connect(str(silver_path)) as silver,
    ):
        service.initialize_legacy_silver(silver)
        context = service.observe_legacy_bronze(bronze, pins=pins)
        result = service.persist_legacy_silver(
            bronze,
            silver,
            pins=pins,
            expected_source_context_sha256=codec.sha(context),
            actor_id="synthetic",
            code_revision="a" * 40,
        )
    pipeline = bronze_target, silver_path, pins, context
    assert json.loads(read(pipeline, result)[0])["legacy_derived_fields"]["iv"] == (0.2).hex()


def test_first_write_precedes_source_reads(pipeline, monkeypatch):
    build(pipeline)

    def forbidden(*args, **kwargs):
        raise AssertionError("source read after prior obligation")

    monkeypatch.setattr(service, "observe_legacy_bronze", forbidden)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(pipeline)


def test_full_bronze_metadata_drift_same_prices(pipeline):
    with duckdb.connect(str(pipeline[0])) as conn:
        conn.execute("UPDATE bronze.event_variants SET recorded_at=recorded_at+INTERVAL 1 SECOND")
    with pytest.raises(ValueError, match="CONTEXT_CHANGED"):
        build(pipeline)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(pipeline)


@pytest.mark.parametrize(
    "sql,reason",
    [
        ("UPDATE {observations} SET volume=1", "RECOMPUTATION"),
        ("UPDATE {observations} SET record_bytes='bad'::BLOB", "RECOMPUTATION"),
        ("DELETE FROM {observations}", "COVERAGE"),
        ("DELETE FROM {attempts}", "COVERAGE"),
        ("DELETE FROM {job_events} WHERE state='SUCCEEDED'", "AUDIT"),
        ("UPDATE {dataset_contracts} SET fingerprint='bad'", "CONTRACT"),
    ],
)
def test_reader_corruption_and_missing_obligations(pipeline, sql, reason):
    result = build(pipeline)
    with duckdb.connect(str(pipeline[1])) as conn:
        tables = {
            "observations": service.name(conn, "silver", "legacy_observations"),
            "attempts": service.name(conn, "silver", "legacy_attempts"),
            "job_events": service.name(conn, "medallion_audit", "job_events"),
            "dataset_contracts": service.name(conn, "medallion_audit", "dataset_contracts"),
        }
        conn.execute(sql.format(**tables))
    with pytest.raises(ValueError, match=reason):
        read(pipeline, result)


@pytest.mark.parametrize("state", ["PLANNED", "RUNNING", "FAILED", "CANCELLED"])
def test_unlinked_scoped_failure_cannot_be_filtered_out(pipeline, state):
    result = build(pipeline)
    with duckdb.connect(str(pipeline[1])) as conn:
        job = AuditLedger(conn).plan_job(
            command_name=service.COMMAND,
            actor_id="synthetic",
            scope_ref="sha256:" + pipeline[2].scope_id,
            code_revision="a" * 40,
            config_hash="b" * 64,
        )
        if state != "PLANNED":
            AuditLedger(conn).transition(job, JobState(state))
    with pytest.raises(ValueError, match="COVERAGE_BOUND"):
        read(pipeline, result)


def test_final_audit_failure_not_adoptable(pipeline, monkeypatch):
    original = AuditLedger.transition

    def transition(self, job_id, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("SYNTHETIC_FINAL_AUDIT")
        return original(self, job_id, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", transition)
    with pytest.raises(RuntimeError, match="FINAL_AUDIT"):
        build(pipeline)
    monkeypatch.setattr(AuditLedger, "transition", original)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(pipeline)
    with duckdb.connect(str(pipeline[1]), read_only=True) as conn:
        sets = service.name(conn, "silver", "legacy_sets")
        job_events = service.name(conn, "medallion_audit", "job_events")
        assert conn.execute(f"SELECT count(*) FROM {sets}").fetchone() == (1,)
        assert conn.execute(
            f"SELECT state FROM {job_events} ORDER BY event_index DESC LIMIT 1"
        ).fetchone() == ("RUNNING",)


def test_domain_rollback_keeps_failed_obligation(pipeline, monkeypatch):
    original = codec.record_values

    def fail(raw):
        original(raw)
        raise RuntimeError("SYNTHETIC_ROW_WRITE_PREPARATION")

    monkeypatch.setattr(codec, "record_values", fail)
    with pytest.raises(RuntimeError, match="PREPARATION"):
        build(pipeline)
    monkeypatch.setattr(codec, "record_values", original)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(pipeline)
    with duckdb.connect(str(pipeline[1]), read_only=True) as conn:
        sets = service.name(conn, "silver", "legacy_sets")
        observations = service.name(conn, "silver", "legacy_observations")
        assert conn.execute(f"SELECT count(*) FROM {sets}").fetchone() == (0,)
        assert conn.execute(f"SELECT count(*) FROM {observations}").fetchone() == (0,)


def test_retained_recording_separate_from_current_bronze(pipeline):
    result = build(pipeline)
    with duckdb.connect(str(pipeline[0])) as conn:
        conn.execute("DELETE FROM medallion_audit.job_events WHERE state='SUCCEEDED'")
    assert len(read(pipeline, result)) == 1
    with pytest.raises(ValueError, match="AUDIT"):
        read(pipeline, result, current=True)


def test_recording_metadata_pin_and_timezone(pipeline):
    result = build(pipeline)
    with duckdb.connect(str(pipeline[1]), read_only=True) as conn:
        conn.execute("SET TimeZone='Asia/Kolkata'")
        assert (
            len(
                service.read_legacy_silver(
                    conn,
                    revision_id=result["revision_id"],
                    expected_recording_fingerprint=result["recording_fingerprint"],
                )
            )
            == 1
        )
    with duckdb.connect(str(pipeline[1])) as conn:
        sets = service.name(conn, "silver", "legacy_sets")
        conn.execute(f"UPDATE {sets} SET recorded_at=recorded_at+INTERVAL 1 SECOND")
    with pytest.raises(ValueError):
        read(pipeline, result)


def test_same_file_cursor_alias_refused_parent_usable(pipeline):
    with duckdb.connect(str(pipeline[0]), read_only=True) as bronze:
        alias = bronze.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                service.persist_legacy_silver(
                    bronze,
                    alias,
                    pins=pipeline[2],
                    expected_source_context_sha256=codec.sha(pipeline[3]),
                    actor_id="synthetic",
                    code_revision="a" * 40,
                )
            assert bronze.execute("SELECT 1").fetchone() == (1,)
        finally:
            alias.close()


def test_source_operational_errors_propagate(pipeline):
    with duckdb.connect(str(pipeline[0])) as conn:
        conn.execute("DROP TABLE bronze.event_variants")
    with pytest.raises(duckdb.Error):
        build(pipeline)


def test_original_bronze_clocks_remain_import_clocks(pipeline):
    result = build(pipeline)
    row = json.loads(read(pipeline, result)[0])
    assert row["stored_fields"]["ts"] == datetime(2026, 1, 1, tzinfo=UTC).isoformat()
    assert row["economic_validity_verified"] is False


def test_orphan_rows_refused_before_source_read(pipeline, monkeypatch):
    build(pipeline)
    with duckdb.connect(str(pipeline[1])) as conn:
        sets = service.name(conn, "silver", "legacy_sets")
        attempts = service.name(conn, "silver", "legacy_attempts")
        job_events = service.name(conn, "medallion_audit", "job_events")
        jobs = service.name(conn, "medallion_audit", "jobs")
        conn.execute(f"DELETE FROM {sets}")
        conn.execute(f"DELETE FROM {attempts}")
        conn.execute(f"DELETE FROM {job_events}")
        conn.execute(f"DELETE FROM {jobs}")

    def forbidden(*args, **kwargs):
        raise AssertionError("orphan source must not be read")

    monkeypatch.setattr(service, "observe_legacy_bronze", forbidden)
    with pytest.raises(ValueError, match="ORPHAN"):
        build(pipeline)


def test_existing_target_not_reinitialized(pipeline):
    with duckdb.connect(str(pipeline[1])) as conn:
        with pytest.raises(ValueError, match="EMPTY"):
            service.initialize_legacy_silver(conn)
        sets = service.name(conn, "silver", "legacy_sets")
        assert conn.execute(f"SELECT count(*) FROM {sets}").fetchone() == (0,)
