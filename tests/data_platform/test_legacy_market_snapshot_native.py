"""Repository native integration: actual Bronze/audit producers, no successful substitutes.

Supplied for repository QA; not executed in the delivery sandbox.
"""

from datetime import UTC, datetime

import duckdb
import pytest
from test_legacy_market_snapshot import capture
from test_legacy_market_snapshot import legacy as legacy

from nse_quant.data_platform import legacy_market_snapshot as service
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore


@pytest.fixture
def target(tmp_path):
    path = tmp_path / "native.duckdb"
    with duckdb.connect(str(path)) as conn:
        BronzeEventStore(conn).initialize()
        AuditLedger(conn).initialize()
    return path


def run(legacy, target, **changes):
    pin = capture(legacy).snapshot_id
    args = dict(
        table="spot_candles",
        source_label="fixture",
        expected_snapshot_id=pin,
        imported_at=datetime(2026, 2, 1, tzinfo=UTC),
        actor_id="synthetic",
        code_revision="a" * 40,
    )
    args.update(changes)
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(target)) as bronze,
    ):
        return service.preserve_legacy_snapshot(source, bronze, **args)


def read(target, result):
    with duckdb.connect(str(target), read_only=True) as conn:
        return service.read_preserved_legacy_snapshot(
            conn,
            capture_event_id=result["capture_event_id"],
            envelope_hash=result["envelope_hash"],
            expected_snapshot_id=result["snapshot_id"],
        )


def test_real_native_preservation_and_projection(legacy, target):
    result = run(legacy, target)
    rows = read(target, result)
    assert len(rows) == result["row_count"] == 1
    assert rows[0]["stored_fields"]["volume"] == "0"
    assert rows[0]["stored_fields"]["oi"] is None
    assert rows[0]["decision_eligibility_asserted"] is False


def test_first_write_refused_before_source_capture(legacy, target):
    run(legacy, target)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        run(legacy, target)
    with duckdb.connect(str(target), read_only=True) as conn:
        assert conn.execute("SELECT count(*) FROM medallion_audit.jobs").fetchone() == (1,)


def test_reviewed_pin_mismatch_records_failed_obligation(legacy, target):
    with pytest.raises(ValueError, match="SOURCE_CHANGED"):
        run(legacy, target, expected_snapshot_id="0" * 64)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        run(legacy, target, expected_snapshot_id="0" * 64)
    with duckdb.connect(str(target), read_only=True) as conn:
        assert conn.execute("SELECT count(*) FROM bronze.event_variants").fetchone() == (0,)
        assert conn.execute(
            "SELECT state FROM medallion_audit.job_events ORDER BY event_index DESC LIMIT 1"
        ).fetchone() == ("FAILED",)


@pytest.mark.parametrize(
    "sql,reason",
    [
        ("UPDATE bronze.event_variants SET payload='bad'::BLOB", "SNAPSHOT"),
        ("DELETE FROM medallion_audit.job_events WHERE state='SUCCEEDED'", "AUDIT"),
        ("UPDATE bronze.ingest_batches SET inserted_variants=2", "BATCH"),
        ("DELETE FROM bronze.input_artifacts", "BATCH"),
    ],
)
def test_original_obligation_and_content_corruption(legacy, target, sql, reason):
    result = run(legacy, target)
    with duckdb.connect(str(target)) as conn:
        conn.execute(sql)
    with pytest.raises(ValueError, match=reason):
        read(target, result)


def test_final_audit_failure_keeps_domain_and_never_adopts(legacy, target, monkeypatch):
    original = AuditLedger.transition

    def transition(self, job_id, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("SYNTHETIC_FINAL_AUDIT_FAILURE")
        return original(self, job_id, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", transition)
    with pytest.raises(RuntimeError, match="SYNTHETIC_FINAL"):
        run(legacy, target)
    monkeypatch.setattr(AuditLedger, "transition", original)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        run(legacy, target)
    with duckdb.connect(str(target), read_only=True) as conn:
        assert conn.execute("SELECT count(*) FROM bronze.event_variants").fetchone() == (1,)
        assert conn.execute(
            "SELECT state FROM medallion_audit.job_events ORDER BY event_index DESC LIMIT 1"
        ).fetchone() == ("RUNNING",)


def test_original_preservation_not_current_source_claim(legacy, target):
    result = run(legacy, target)
    with duckdb.connect(str(legacy)) as conn:
        conn.execute("UPDATE spot_candles SET close=5")
    assert len(read(target, result)) == 1
    assert capture(legacy).snapshot_id != result["snapshot_id"]


def test_domain_failure_rolls_back_and_keeps_failed_audit(legacy, target):
    with duckdb.connect(str(target)) as conn:
        conn.execute("DROP TABLE bronze.input_artifacts")
    with pytest.raises(duckdb.Error):
        run(legacy, target)
    with duckdb.connect(str(target), read_only=True) as conn:
        assert conn.execute("SELECT count(*) FROM bronze.event_variants").fetchone() == (0,)
        assert conn.execute(
            "SELECT state FROM medallion_audit.job_events ORDER BY event_index DESC LIMIT 1"
        ).fetchone() == ("FAILED",)


def test_same_live_file_cursor_alias_refused(legacy):
    pin = capture(legacy).snapshot_id
    with duckdb.connect(str(legacy), read_only=True) as source:
        cursor = source.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE_NATIVE"):
                service.preserve_legacy_snapshot(
                    source,
                    cursor,
                    table="spot_candles",
                    source_label="fixture",
                    expected_snapshot_id=pin,
                    imported_at=datetime(2026, 2, 1, tzinfo=UTC),
                    actor_id="synthetic",
                    code_revision="a" * 40,
                )
            assert source.execute("SELECT 1").fetchone() == (1,)
        finally:
            cursor.close()
