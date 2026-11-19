"""Actual strategy-position writer -> native Bronze; no close/P&L attestation."""

from datetime import UTC, date, datetime

import duckdb
import pytest

from nse_quant.core.models import StrategyPosition
from nse_quant.data_platform import legacy_strategy_positions as codec
from nse_quant.data_platform import legacy_strategy_positions_bronze as native
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.persistence.repositories import PositionRepository

OPENED = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
CLOSED = datetime(2026, 1, 1, 15, 30, tzinfo=UTC)
IMPORT_AT = datetime(2026, 1, 2, tzinfo=UTC)
REVISION = "a" * 40
EXPIRY = date(2026, 1, 29)


def strategy_position(**changes):
    values = dict(
        strategy_position_id="A",
        proposal_id="P",
        strategy="iron_condor",
        underlying="NIFTY",
        expiry=EXPIRY,
        opened_at=OPENED,
        entry_price=100.5,
        current_price=101.25,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        status="OPEN",
        exit_reason=None,
        all_triggered_exits=[],
        closed_at=None,
        thesis="original thesis",
        metadata={"synthetic": True},
    )
    values.update(changes)
    return StrategyPosition(**values)


def seed(path):
    legacy = DuckDBStore(path=path)
    try:
        repository = PositionRepository(legacy.conn)
        repository.create_strategy_position(strategy_position())
        repository.create_strategy_position(
            strategy_position(
                strategy_position_id="B",
                status="CLOSED",
                exit_reason="target_profit",
                all_triggered_exits=["target_profit"],
                closed_at=CLOSED,
                realized_pnl=125.0,
            )
        )
        table = native.common.name(legacy.conn, "main", codec.TABLE)
        legacy.conn.execute(
            f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CAST(? AS JSON))",
            [
                "C",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                "OPEN",
                None,
                None,
                CLOSED,
                None,
                '{"duplicate":1,"duplicate":2}',
            ],
        )
    finally:
        legacy.close()


def record(tmp_path):
    legacy, bronze = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy)
    with duckdb.connect(str(legacy), read_only=True) as source, duckdb.connect(str(bronze)) as b:
        AuditLedger(b).initialize()
        BronzeEventStore(b).initialize()
        snapshot = native.capture_strategy_positions(source, source_label="fixture")
        result = native.preserve_strategy_positions(
            source,
            b,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=IMPORT_AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return legacy, bronze, result


def args(result):
    return dict(
        source_label=result["source_label"],
        snapshot_id=result["snapshot_id"],
        capture_event_id=result["capture_event_id"],
        envelope_hash=result["envelope_hash"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )


def read(path, result):
    with duckdb.connect(str(path), read_only=True) as connection:
        return native.read_strategy_positions_bronze(connection, **args(result))


def test_actual_writer_and_native_chain_retain_every_field(tmp_path):
    legacy, bronze, result = record(tmp_path)
    rows = read(bronze, result)
    assert len(rows) == result["row_count"] == 3
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(bronze), read_only=True) as connection,
    ):
        assert (
            native.revalidate_strategy_positions_source(source, connection, **args(result)) == rows
        )
        table = native.common.name(source, "main", codec.TABLE)
        originals = source.execute(f"SELECT * FROM {table}").fetchall()
        by_id = {row[0]: row for row in originals}
        for ordinal, raw in enumerate(rows):
            document = codec.parse(raw, codec.MAX_RECORD)
            fields = document["stored_fields"]
            assert document["source_ordinal"] == ordinal
            assert fields["strategy_position_id"] in by_id
            assert not document["original_position_execution_replayed"]
            assert not document["native_decision_replayed"]
            assert not document["decision_eligibility_asserted"]
        assert by_id["A"][5] == OPENED and by_id["A"][6] == 100.5
        assert by_id["A"][7] == 101.25 and by_id["A"][14] == "original thesis"
        assert by_id["B"][10] == "CLOSED" and by_id["B"][11] == "target_profit"
        assert by_id["B"][12] == '["target_profit"]' and by_id["B"][13] == CLOSED
        assert by_id["B"][8] == 125.0
        assert by_id["C"][0:10] == ("C",) + (None,) * 9
        assert by_id["C"][13] == CLOSED
        assert by_id["C"][15] == '{"duplicate":1,"duplicate":2}'
        flagged = [codec.parse(raw, codec.MAX_RECORD) for raw in rows]
        assert any("CLOSED_AT_WITHOUT_CLOSED_STATUS" in item["flags"] for item in flagged)


def test_retained_strategy_position_is_not_native_truth(tmp_path):
    _legacy, bronze, result = record(tmp_path)
    for raw in read(bronze, result):
        document = codec.parse(raw, codec.MAX_RECORD)
        assert document["classification"] == ("RETAINED_LEGACY_STRATEGY_POSITION_NOT_NATIVE_TRUTH")
        assert not document["exit_reason_interpreted"]
        assert not document["triggered_exits_interpreted"]
        assert not document["thesis_interpreted"]
        assert not document["metadata_interpreted"]
        assert not document["pnl_interpreted"]
        assert not document["publication_asserted"]
        assert not document["decision_eligibility_asserted"]


@pytest.mark.parametrize(
    "kind",
    ["payload", "artifact", "event-id", "audit", "clock"],
    ids=["payload", "artifact", "id", "audit", "clock"],
)
def test_original_native_recording_tampering(tmp_path, kind):
    _legacy, bronze, result = record(tmp_path)
    with duckdb.connect(str(bronze)) as connection:
        variants = native.common.name(connection, "bronze", "event_variants")
        if kind == "payload":
            connection.execute(f"UPDATE {variants} SET payload='bad'::BLOB")
        elif kind == "artifact":
            table = native.common.name(connection, "bronze", "input_artifacts")
            connection.execute(f"UPDATE {table} SET artifact_bytes='bad'::BLOB")
        elif kind == "event-id":
            connection.execute(f"UPDATE {variants} SET capture_event_id=?", ["f" * 64])
        elif kind == "audit":
            table = native.common.name(connection, "medallion_audit", "job_events")
            connection.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
        else:
            connection.execute(f"UPDATE {variants} SET recorded_at=recorded_at+INTERVAL '1 second'")
    with pytest.raises(ValueError):
        read(bronze, result)


def test_changed_review_pin_cannot_heal_source_scope(tmp_path):
    legacy, bronze = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy)
    with duckdb.connect(str(legacy), read_only=True) as source, duckdb.connect(str(bronze)) as b:
        AuditLedger(b).initialize()
        BronzeEventStore(b).initialize()
        snapshot = native.capture_strategy_positions(source, source_label="fixture")
        with pytest.raises(ValueError, match="REVIEWED_STRATEGY_POSITION_SOURCE_CHANGED"):
            native.preserve_strategy_positions(
                source,
                b,
                source_label="fixture",
                expected_snapshot_id="0" * 64,
                imported_at=IMPORT_AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            native.preserve_strategy_positions(
                source,
                b,
                source_label="fixture",
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=IMPORT_AT,
                actor_id="other",
                code_revision="b" * 40,
            )


def test_extra_scoped_job_not_hidden(tmp_path):
    _legacy, bronze, result = record(tmp_path)
    with duckdb.connect(str(bronze)) as connection:
        ledger = AuditLedger(connection)
        job = ledger.plan_job(
            command_name=native.COMMAND,
            actor_id="synthetic",
            code_revision=REVISION,
            scope_ref="sha256:" + native.scope_id("fixture"),
            config_hash="b" * 64,
        )
        ledger.transition(job, JobState.FAILED, "EXECUTION_ERROR")
    with pytest.raises(ValueError):
        read(bronze, result)


def test_retained_native_and_current_legacy_are_distinct(tmp_path):
    legacy, bronze, result = record(tmp_path)
    with duckdb.connect(str(legacy)) as connection:
        table = native.common.name(connection, "main", codec.TABLE)
        connection.execute(f"UPDATE {table} SET status='CHANGED'")
    assert len(read(bronze, result)) == 3
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(bronze), read_only=True) as connection,
        pytest.raises(ValueError, match="CURRENT"),
    ):
        native.revalidate_strategy_positions_source(source, connection, **args(result))


def test_injected_variant_sql_failure_rolls_back_native_rows(tmp_path):
    legacy, bronze = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy)
    with duckdb.connect(str(legacy), read_only=True) as source, duckdb.connect(str(bronze)) as b:
        AuditLedger(b).initialize()
        BronzeEventStore(b).initialize()
        snapshot = native.capture_strategy_positions(source, source_label="fixture")

        class Fail:
            def execute(self, sql, parameters=None):
                if sql.lstrip().startswith("INSERT INTO") and '"event_variants"' in sql:
                    raise RuntimeError("INJECTED_STRATEGY_POSITION_VARIANT_SQL_FAILURE")
                return b.execute(sql) if parameters is None else b.execute(sql, parameters)

        with pytest.raises(RuntimeError, match="VARIANT_SQL_FAILURE"):
            native.preserve_strategy_positions(
                source,
                Fail(),
                source_label="fixture",
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=IMPORT_AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        for name in ("event_variants", "input_artifacts", "ingest_batches"):
            table = native.common.name(b, "bronze", name)
            assert b.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            native.preserve_strategy_positions(
                source,
                b,
                source_label="fixture",
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=IMPORT_AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )


def test_final_audit_failure_blocks_original_recording(tmp_path, monkeypatch):
    legacy, bronze = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy)
    original = AuditLedger.transition

    def fail(self, job, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("SYNTHETIC_STRATEGY_POSITION_FINAL_AUDIT")
        return original(self, job, state, reason_code)

    with duckdb.connect(str(legacy), read_only=True) as source, duckdb.connect(str(bronze)) as b:
        AuditLedger(b).initialize()
        BronzeEventStore(b).initialize()
        snapshot = native.capture_strategy_positions(source, source_label="fixture")
        monkeypatch.setattr(AuditLedger, "transition", fail)
        with pytest.raises(RuntimeError, match="FINAL_AUDIT"):
            native.preserve_strategy_positions(
                source,
                b,
                source_label="fixture",
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=IMPORT_AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        monkeypatch.setattr(AuditLedger, "transition", original)
        table = native.common.name(b, "bronze", "event_variants")
        row = b.execute(f"SELECT capture_event_id,envelope_hash FROM {table}").fetchone()
        assert row is not None
    with (
        duckdb.connect(str(bronze), read_only=True) as connection,
        pytest.raises(ValueError, match="AUDIT_NOT_VERIFIED"),
    ):
        native.read_strategy_positions_bronze(
            connection,
            source_label="fixture",
            snapshot_id=snapshot.snapshot_id,
            capture_event_id=row[0],
            envelope_hash=row[1],
            expected_recording_fingerprint="a" * 64,
        )


def test_timezone_readonly_and_same_live_alias(tmp_path):
    legacy, bronze, result = record(tmp_path)
    with duckdb.connect(str(legacy), read_only=True) as source:
        first = native.capture_strategy_positions(source, source_label="fixture")
        source.execute("SET TimeZone='Asia/Kolkata'")
        assert native.capture_strategy_positions(source, source_label="fixture") == first
    with duckdb.connect(str(bronze)) as connection:
        with pytest.raises(ValueError, match="READONLY"):
            native.read_strategy_positions_bronze(connection, **args(result))
        alias = connection.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                native.preserve_strategy_positions(
                    alias,
                    connection,
                    source_label="fixture",
                    expected_snapshot_id=result["snapshot_id"],
                    imported_at=IMPORT_AT,
                    actor_id="synthetic",
                    code_revision=REVISION,
                )
            assert connection.execute("SELECT 1").fetchone() == (1,)
        finally:
            alias.close()
