"""Synthetic actual SQL -> native Bronze -> persisted Silver producer/reader tests."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import legacy_daily_rv as codec
from nse_quant.data_platform import legacy_daily_rv_bronze as bronze_api
from nse_quant.data_platform import legacy_daily_rv_silver_store as silver
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore

REVISION = "a" * 40
AT = datetime(2026, 1, 1, tzinfo=UTC)


def _bronze(tmp_path: Path, symbol: str = "NIFTY") -> tuple[Path, silver.DailyRVBronzePins]:
    legacy_path = tmp_path / "legacy.duckdb"
    bronze_path = tmp_path / "bronze.duckdb"
    writer = duckdb.connect(str(legacy_path))
    try:
        table = bronze_api.name(writer, "main", codec.TABLE)
        writer.execute(
            f"CREATE TABLE {table} (symbol VARCHAR NOT NULL,trading_date DATE NOT NULL,"
            "rv DOUBLE NOT NULL,observation_count BIGINT NOT NULL,"
            "PRIMARY KEY(symbol,trading_date))"
        )
        writer.executemany(
            f"INSERT INTO {table} VALUES (?,DATE '2026-01-01',?,?)",
            [(symbol, -0.0, 0), ("BANK", -0.25, -2), ("OTHER", 0.5, 30)],
        )
    finally:
        writer.close()
    source = duckdb.connect(str(legacy_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = bronze_api.capture_daily_rv(source, source_label="fixture")
        receipt = bronze_api.preserve_daily_rv(
            source,
            target,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
        pins = silver.DailyRVBronzePins(
            "fixture",
            receipt["snapshot_id"],
            receipt["capture_event_id"],
            receipt["envelope_hash"],
            receipt["recording_fingerprint"],
        )
    finally:
        target.close()
        source.close()
    return bronze_path, pins


def _silver(tmp_path: Path) -> tuple[Path, Path, silver.DailyRVBronzePins, dict[str, Any]]:
    path, pins = _bronze(tmp_path)
    silver_path = tmp_path / "silver.duckdb"  # Preserve actual catalog/schema collision.
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(silver_path))
    try:
        silver.initialize_daily_rv_silver(target)
        context = silver.observe_daily_rv_bronze(bronze, pins=pins)
        receipt = silver.persist_daily_rv_silver(
            bronze,
            target,
            pins=pins,
            expected_context_sha256=codec.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    finally:
        target.close()
        bronze.close()
    return path, silver_path, pins, receipt


def _args(receipt: dict[str, Any]) -> dict[str, str]:
    return dict(
        revision_id=receipt["revision_id"],
        expected_recording_fingerprint=receipt["recording_fingerprint"],
    )


def test_actual_native_chain_and_full_replay(tmp_path: Path) -> None:
    path, silver_path, pins, receipt = _silver(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        actual = silver.read_daily_rv_silver(reader, **_args(receipt))
        assert actual == bronze_api.read_daily_rv_bronze(bronze, **pins.reader_args())
        assert silver.revalidate_daily_rv_silver(bronze, reader, **_args(receipt)) == actual
        assert len(actual) == 3
        docs = [json.loads(r) for r in actual]
        assert [d["source_ordinal"] for d in docs] == [0, 1, 2]
        by_symbol = {d["stored_fields"]["symbol"]: d for d in docs}
        assert by_symbol["NIFTY"]["stored_fields"]["rv"] == (-0.0).hex()
        assert by_symbol["BANK"]["flags"] == ["NEGATIVE_LEGACY_RV", "NONPOSITIVE_OBSERVATION_COUNT"]
        for doc in docs:
            assert doc["native_rv_recomputed"] is False
            assert doc["original_availability_at"] is None
            assert doc["decision_eligibility_asserted"] is False
    finally:
        reader.close()
        bronze.close()


def test_retained_silver_does_not_probe_missing_bronze(tmp_path: Path) -> None:
    path, silver_path, _pins, receipt = _silver(tmp_path)
    path.unlink()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        assert len(silver.read_daily_rv_silver(reader, **_args(receipt))) == 3
    finally:
        reader.close()


def test_changed_bronze_audit_only_blocks_current_revalidation(tmp_path: Path) -> None:
    path, silver_path, _pins, receipt = _silver(tmp_path)
    writer = duckdb.connect(str(path))
    try:
        writer.execute(
            f"DELETE FROM {bronze_api.name(writer, 'medallion_audit', 'job_events')} "
            "WHERE state='SUCCEEDED'"
        )
    finally:
        writer.close()
    bronze = duckdb.connect(str(path), read_only=True)
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        assert len(silver.read_daily_rv_silver(reader, **_args(receipt))) == 3
        with pytest.raises(codec.Rejected, match="ORIGINAL_AUDIT_NOT_VERIFIED"):
            silver.revalidate_daily_rv_silver(bronze, reader, **_args(receipt))
    finally:
        reader.close()
        bronze.close()


def test_wrong_context_cannot_heal_with_new_recording_pin(tmp_path: Path) -> None:
    path, pins = _bronze(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "silver.duckdb"))
    try:
        silver.initialize_daily_rv_silver(target)
        with pytest.raises(codec.Rejected, match="REVIEWED_BRONZE_CONTEXT_CHANGED"):
            silver.persist_daily_rv_silver(
                bronze,
                target,
                pins=pins,
                expected_context_sha256="b" * 64,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        changed = replace(pins, recording_fingerprint="c" * 64, envelope_hash="d" * 64)
        assert changed.scope_id == pins.scope_id
        with pytest.raises(codec.Rejected, match="SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"):
            silver.persist_daily_rv_silver(
                bronze,
                target,
                pins=changed,
                expected_context_sha256="e" * 64,
                actor_id="other",
                code_revision="f" * 40,
            )
    finally:
        target.close()
        bronze.close()


@pytest.mark.parametrize(
    "kind",
    ["scalar", "bytes", "ordinal", "missing", "context", "link", "audit", "clock", "oversized"],
    ids=[
        "scalar",
        "bytes",
        "ordinal",
        "missing",
        "context",
        "link",
        "audit",
        "clock",
        "oversized-record",
    ],
)
def test_silver_tampering_rejects(tmp_path: Path, kind: str) -> None:
    _path, silver_path, _pins, receipt = _silver(tmp_path)
    writer = duckdb.connect(str(silver_path))
    try:
        records = bronze_api.name(writer, "silver", "rv_observations")
        sets = bronze_api.name(writer, "silver", "rv_sets")
        if kind == "scalar":
            writer.execute(f"UPDATE {records} SET observation_count=99 WHERE ordinal=0")
        elif kind == "bytes":
            writer.execute(f"UPDATE {records} SET record_bytes=? WHERE ordinal=0", [b"{}"])
        elif kind == "ordinal":
            writer.execute(f"UPDATE {records} SET ordinal=9 WHERE ordinal=0")
        elif kind == "missing":
            writer.execute(f"DELETE FROM {records} WHERE ordinal=0")
        elif kind == "context":
            writer.execute(f"UPDATE {sets} SET context=?", [b"{}"])
        elif kind == "link":
            writer.execute(f"DELETE FROM {bronze_api.name(writer, 'silver', 'rv_attempts')}")
        elif kind == "audit":
            audit_events = bronze_api.name(writer, "medallion_audit", "job_events")
            writer.execute(f"DELETE FROM {audit_events} WHERE state='SUCCEEDED'")
        elif kind == "clock":
            writer.execute(f"UPDATE {sets} SET recorded_at=recorded_at+INTERVAL '1 second'")
            writer.execute(f"UPDATE {records} SET recorded_at=recorded_at+INTERVAL '1 second'")
        else:
            writer.execute(
                f"UPDATE {records} SET record_bytes=? WHERE ordinal=0",
                [b"x" * (codec.MAX_RECORD + 1)],
            )
    finally:
        writer.close()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        with pytest.raises(codec.Rejected):
            silver.read_daily_rv_silver(reader, **_args(receipt))
    finally:
        reader.close()


def test_sql_domain_failure_rolls_back_and_blocks_retry(tmp_path: Path) -> None:
    path, pins = _bronze(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    owner = duckdb.connect(str(tmp_path / "silver.duckdb"))

    class FailingConnection:
        def __init__(self) -> None:
            self.insert_count = 0

        def execute(self, sql: str, parameters: Any = None) -> Any:
            if sql.startswith("INSERT INTO") and '"rv_observations"' in sql:
                self.insert_count += 1
                if self.insert_count == 2:
                    raise RuntimeError("INJECTED_SILVER_INSERT_FAILURE")
            return owner.execute(sql) if parameters is None else owner.execute(sql, parameters)

    try:
        silver.initialize_daily_rv_silver(owner)
        context = silver.observe_daily_rv_bronze(bronze, pins=pins)
        with pytest.raises(RuntimeError, match="INJECTED_SILVER_INSERT_FAILURE"):
            silver.persist_daily_rv_silver(
                bronze,
                FailingConnection(),
                pins=pins,
                expected_context_sha256=codec.sha(context),
                actor_id="synthetic",
                code_revision=REVISION,
            )
        for table in ("rv_sets", "rv_observations", "rv_attempts"):
            q = bronze_api.name(owner, "silver", table)
            assert owner.execute(f"SELECT count(*) FROM {q}").fetchone() == (0,)
        with pytest.raises(codec.Rejected, match="SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"):
            silver.persist_daily_rv_silver(
                bronze,
                owner,
                pins=pins,
                expected_context_sha256=codec.sha(context),
                actor_id="synthetic",
                code_revision=REVISION,
            )
    finally:
        owner.close()
        bronze.close()


def test_final_audit_failure_leaves_unreadable_original(tmp_path: Path, monkeypatch: Any) -> None:
    path, pins = _bronze(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "silver.duckdb"))
    original = AuditLedger.transition

    def fail(self: Any, job: str, state: JobState, reason_code: str | None = None) -> None:
        if state == JobState.SUCCEEDED:
            raise RuntimeError("INJECTED_FINAL_AUDIT_FAILURE")
        original(self, job, state, reason_code)

    try:
        silver.initialize_daily_rv_silver(target)
        context = silver.observe_daily_rv_bronze(bronze, pins=pins)
        monkeypatch.setattr(AuditLedger, "transition", fail)
        with pytest.raises(RuntimeError, match="INJECTED_FINAL_AUDIT_FAILURE"):
            silver.persist_daily_rv_silver(
                bronze,
                target,
                pins=pins,
                expected_context_sha256=codec.sha(context),
                actor_id="synthetic",
                code_revision=REVISION,
            )
        table = bronze_api.name(target, "silver", "rv_sets")
        row = target.execute(f"SELECT revision_id FROM {table}").fetchone()
        assert row is not None
        revision = row[0]
        with pytest.raises(codec.Rejected, match="SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"):
            silver.persist_daily_rv_silver(
                bronze,
                target,
                pins=pins,
                expected_context_sha256=codec.sha(context),
                actor_id="synthetic",
                code_revision=REVISION,
            )
    finally:
        target.close()
        bronze.close()
    reader = duckdb.connect(str(tmp_path / "silver.duckdb"), read_only=True)
    try:
        with pytest.raises(codec.Rejected, match="ORIGINAL_SILVER_AUDIT_NOT_VERIFIED"):
            silver.read_daily_rv_silver(
                reader, revision_id=revision, expected_recording_fingerprint="b" * 64
            )
    finally:
        reader.close()


def test_same_live_file_alias_rejected_parent_survives(tmp_path: Path) -> None:
    target = duckdb.connect(str(tmp_path / "silver.duckdb"))
    alias = target.cursor()
    pins = silver.DailyRVBronzePins("fixture", "a" * 64, "b" * 64, "c" * 64, "d" * 64)
    try:
        silver.initialize_daily_rv_silver(target)
        with pytest.raises(codec.Rejected, match="SEPARATE_TARGET_REQUIRED"):
            silver.persist_daily_rv_silver(
                alias,
                target,
                pins=pins,
                expected_context_sha256="e" * 64,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        assert target.execute("SELECT 1").fetchone() == (1,)
    finally:
        alias.close()
        target.close()


def test_context_hex_bound_before_decode() -> None:
    pins = silver.DailyRVBronzePins("fixture", "a" * 64, "b" * 64, "c" * 64, "d" * 64)
    raw = codec.canonical(
        dict(
            version=silver.VERSION, pins=asdict(pins), snapshot_hex="z" * (2 * codec.MAX_BYTES + 1)
        )
    )
    with pytest.raises(codec.Rejected, match="SNAPSHOT_HEX_BOUND"):
        silver._derive(raw)


def test_no_reinitialize_or_foreign_table_adoption(tmp_path: Path) -> None:
    target = duckdb.connect(str(tmp_path / "silver.duckdb"))
    try:
        silver.initialize_daily_rv_silver(target)
        with pytest.raises(codec.Rejected, match="EMPTY_SILVER_INITIALIZATION_REQUIRED"):
            silver.initialize_daily_rv_silver(target)
    finally:
        target.close()


@pytest.mark.parametrize(
    "kind",
    ["contract", "definition", "duplicate-job", "aggregate"],
    ids=["contract-drift", "definition-drift", "duplicate-job", "aggregate-bound"],
)
def test_definitions_original_jobs_and_aggregate_bound(tmp_path: Path, kind: str) -> None:
    _path, silver_path, pins, receipt = _silver(tmp_path)
    writer = duckdb.connect(str(silver_path))
    try:
        if kind == "contract":
            table = bronze_api.name(writer, "medallion_audit", "dataset_contracts")
            writer.execute(f"UPDATE {table} SET fingerprint=?", ["f" * 64])
        elif kind == "definition":
            table = bronze_api.name(writer, "silver", "rv_versions")
            writer.execute(f"UPDATE {table} SET definition=?", [b"{}"])
        elif kind == "duplicate-job":
            AuditLedger(writer).plan_job(
                command_name=silver.COMMAND,
                actor_id="other",
                scope_ref="sha256:" + pins.scope_id,
                code_revision=REVISION,
                config_hash="f" * 64,
            )
        else:
            table = bronze_api.name(writer, "silver", "rv_observations")
            writer.execute(
                f"UPDATE {table} SET record_bytes=? WHERE ordinal=0",
                [b"x" * (codec.MAX_RECORDS + 1)],
            )
    finally:
        writer.close()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        with pytest.raises(codec.Rejected):
            silver.read_daily_rv_silver(reader, **_args(receipt))
    finally:
        reader.close()


def test_second_actual_observation_then_injected_drift(tmp_path: Path, monkeypatch: Any) -> None:
    path, pins = _bronze(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "silver.duckdb"))
    actual = silver.observe_daily_rv_bronze
    calls = 0

    def drift(conn: Any, *, pins: silver.DailyRVBronzePins) -> bytes:
        nonlocal calls
        context = actual(conn, pins=pins)
        calls += 1
        # Negative-boundary injection after the real source check, not authentic source drift.
        return context + b" " if calls == 2 else context

    try:
        silver.initialize_daily_rv_silver(target)
        reviewed = actual(bronze, pins=pins)
        monkeypatch.setattr(silver, "observe_daily_rv_bronze", drift)
        with pytest.raises(codec.Rejected, match="BRONZE_CONTEXT_DRIFT"):
            silver.persist_daily_rv_silver(
                bronze,
                target,
                pins=pins,
                expected_context_sha256=codec.sha(reviewed),
                actor_id="synthetic",
                code_revision=REVISION,
            )
        records = bronze_api.name(target, "silver", "rv_observations")
        assert target.execute(f"SELECT count(*) FROM {records}").fetchone() == (0,)
    finally:
        target.close()
        bronze.close()


def test_silver_orphan_records_block_adoption(tmp_path: Path) -> None:
    path, silver_path, pins, _receipt = _silver(tmp_path)
    writer = duckdb.connect(str(silver_path))
    try:
        for schema, table in (
            ("silver", "rv_sets"),
            ("silver", "rv_attempts"),
            ("medallion_audit", "job_events"),
            ("medallion_audit", "jobs"),
        ):
            writer.execute(f"DELETE FROM {bronze_api.name(writer, schema, table)}")
    finally:
        writer.close()
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(silver_path))
    try:
        context = silver.observe_daily_rv_bronze(bronze, pins=pins)
        with pytest.raises(codec.Rejected, match="SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"):
            silver.persist_daily_rv_silver(
                bronze,
                target,
                pins=pins,
                expected_context_sha256=codec.sha(context),
                actor_id="synthetic",
                code_revision=REVISION,
            )
    finally:
        target.close()
        bronze.close()


@pytest.mark.parametrize("symbol", ["x" * 65536], ids=["maximum-symbol"])
def test_source_symbol_limit_survives_persisted_silver(tmp_path: Path, symbol: str) -> None:
    path, pins = _bronze(tmp_path, symbol=symbol)
    bronze = duckdb.connect(str(path), read_only=True)
    target_path = tmp_path / "silver.duckdb"
    target = duckdb.connect(str(target_path))
    try:
        silver.initialize_daily_rv_silver(target)
        context = silver.observe_daily_rv_bronze(bronze, pins=pins)
        receipt = silver.persist_daily_rv_silver(
            bronze,
            target,
            pins=pins,
            expected_context_sha256=codec.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    finally:
        target.close()
        bronze.close()
    reader = duckdb.connect(str(target_path), read_only=True)
    try:
        records = silver.read_daily_rv_silver(reader, **_args(receipt))
        assert symbol in {json.loads(r)["stored_fields"]["symbol"] for r in records}
    finally:
        reader.close()
