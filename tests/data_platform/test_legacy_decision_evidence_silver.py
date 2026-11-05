"""Actual legacy writer -> native evidence Bronze -> naive-clock Silver and faults."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import legacy_daily_rv_bronze as common
from nse_quant.data_platform import legacy_decision_evidence as codec
from nse_quant.data_platform import legacy_decision_evidence_bronze as bronze_api
from nse_quant.data_platform import legacy_decision_evidence_silver_store as silver
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore

WALL = datetime(2026, 1, 1, 9, 15, 0, 123456)
IMPORT_AT = datetime(2026, 1, 2, tzinfo=UTC)
REVISION = "a" * 40
OPAQUE = 'not-json: { "available":true, "eligible":true, "eligible":false }'


def _bronze(
    tmp_path: Path, maximum_payload: str | None = None
) -> tuple[Path, silver.EvidenceBronzePins]:
    legacy_path = tmp_path / "legacy.duckdb"
    bronze_path = tmp_path / "bronze.duckdb"
    legacy = DuckDBStore(path=legacy_path)
    try:
        args: dict[str, Any] = dict(run_id="run", ts=WALL, symbol="NIFTY", plugin="plugin-A")
        legacy.write_decision_evidence(**args, evidence={"available": True, "reason": "first"})
        legacy.write_decision_evidence(
            **args, evidence={"available": False, "reason": "replacement"}
        )
        legacy.write_decision_evidence(
            run_id="run",
            ts=WALL + timedelta(seconds=1),
            symbol="NIFTY",
            plugin="plugin-B",
            evidence={"available": True},
        )
        legacy.write_decision_evidence(
            run_id="run",
            ts=datetime(2026, 1, 1, 9, 15, 3),
            symbol="NIFTY",
            plugin="plugin-D",
            evidence={"available": False},
        )
        table = common.name(legacy.conn, "main", codec.TABLE)
        # Explicit opaque-text boundary, not authentic authorization evidence.
        legacy.conn.execute(
            f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?)",
            [
                "opaque",
                "run",
                WALL + timedelta(seconds=2),
                "NIFTY",
                "plugin-C",
                True,
                OPAQUE if maximum_payload is None else maximum_payload,
            ],
        )
    finally:
        legacy.close()
    source = duckdb.connect(str(legacy_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = bronze_api.capture_decision_evidence(source, source_label="fixture")
        receipt = bronze_api.preserve_decision_evidence(
            source,
            target,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=IMPORT_AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
        pins = silver.EvidenceBronzePins(
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


def _chain(tmp_path: Path) -> tuple[Path, Path, silver.EvidenceBronzePins, dict[str, Any]]:
    path, pins = _bronze(tmp_path)
    silver_path = tmp_path / "silver.duckdb"  # Preserve actual catalog/schema collision.
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(silver_path))
    try:
        silver.initialize_decision_evidence_silver(target)
        context = silver.observe_decision_evidence_bronze(bronze, pins=pins)
        receipt = silver.persist_decision_evidence_silver(
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


def test_actual_native_chain_and_session_timezone_invariance(tmp_path: Path) -> None:
    path, silver_path, pins, receipt = _chain(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        records = silver.read_decision_evidence_silver(reader, **_args(receipt))
        assert records == bronze_api.read_decision_evidence_bronze(bronze, **pins.reader_args())
        assert records == silver.revalidate_decision_evidence_silver(
            bronze, reader, **_args(receipt)
        )
        assert len(records) == 4
        columns = ",".join('"' + n + '"' for n, _ in codec.SCHEMA)
        table = common.name(reader, "silver", "evidence_observations")
        rows = reader.execute(f"SELECT {columns} FROM {table} ORDER BY ordinal").fetchall()
        for ordinal, (row, raw) in enumerate(zip(rows, records, strict=True)):
            assert row == silver._values(raw)[2:]
            assert row[2].tzinfo is None
            assert type(row[5]) is bool
            doc = codec.parse(raw, codec.MAX_RECORD)
            assert doc["source_ordinal"] == ordinal
            assert doc["stored_ts_instant"] is None
            assert doc["source_timezone"] is None
            assert doc["original_availability_at"] is None
            assert doc["native_decision_replayed"] is False
            assert doc["decision_eligibility_asserted"] is False
        docs = [codec.parse(raw, codec.MAX_RECORD) for raw in records]
        opaque = next(doc for doc in docs if doc["stored_fields"]["evidence_id"] == "opaque")
        assert opaque["stored_fields"]["payload_json"] == OPAQUE
        assert opaque["stored_fields"]["available"] is True
        for zone in ("UTC", "Asia/Kolkata"):
            reader.execute(f"SET TimeZone='{zone}'")
            assert silver.read_decision_evidence_silver(reader, **_args(receipt)) == records
    finally:
        reader.close()
        bronze.close()


@pytest.mark.parametrize("field,kind", codec.SCHEMA, ids=[n for n, _ in codec.SCHEMA])
def test_all_seven_fields_reconciled(tmp_path: Path, field: str, kind: str) -> None:
    _path, silver_path, _pins, receipt = _chain(tmp_path)
    writer = duckdb.connect(str(silver_path))
    try:
        table = common.name(writer, "silver", "evidence_observations")
        value: object = (
            WALL + timedelta(days=1)
            if kind == "TIMESTAMP"
            else (False if kind == "BOOLEAN" else "changed-field")
        )
        writer.execute(f'UPDATE {table} SET "{field}"=? WHERE evidence_id=?', [value, "opaque"])
    finally:
        writer.close()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        with pytest.raises(
            codec.Rejected, match="EVIDENCE_SILVER_FULL_RECORD_RECOMPUTATION_MISMATCH"
        ):
            silver.read_decision_evidence_silver(reader, **_args(receipt))
    finally:
        reader.close()


@pytest.mark.parametrize(
    "kind",
    [
        "bytes",
        "missing",
        "context",
        "record-bound",
        "aggregate",
        "cell-bound",
        "link",
        "audit",
        "clock",
        "bool-type",
    ],
    ids=[
        "bytes",
        "missing",
        "context",
        "record-bound",
        "aggregate",
        "cell-bound",
        "link",
        "audit",
        "clock",
        "bool-type",
    ],
)
def test_original_recording_faults(tmp_path: Path, kind: str) -> None:
    _path, silver_path, _pins, receipt = _chain(tmp_path)
    writer = duckdb.connect(str(silver_path))
    try:
        table = common.name(writer, "silver", "evidence_observations")
        sets = common.name(writer, "silver", "evidence_sets")
        if kind == "bytes":
            writer.execute(f"UPDATE {table} SET record_bytes=? WHERE ordinal=0", [b"{}"])
        elif kind == "missing":
            writer.execute(f"DELETE FROM {table} WHERE ordinal=0")
        elif kind == "context":
            writer.execute(f"UPDATE {sets} SET context=?", [b"x" * (silver.MAX_CONTEXT + 1)])
        elif kind in ("record-bound", "aggregate"):
            bound = codec.MAX_RECORD if kind == "record-bound" else codec.MAX_RECORDS
            writer.execute(
                f"UPDATE {table} SET record_bytes=? WHERE ordinal=0", [b"x" * (bound + 1)]
            )
        elif kind == "cell-bound":
            writer.execute(
                f"UPDATE {table} SET payload_json=? WHERE ordinal=0", ["x" * (codec.MAX_CELL + 1)]
            )
        elif kind == "link":
            writer.execute(f"DELETE FROM {common.name(writer, 'silver', 'evidence_attempts')}")
        elif kind == "audit":
            events = common.name(writer, "medallion_audit", "job_events")
            writer.execute(f"DELETE FROM {events} WHERE state='SUCCEEDED'")
        elif kind == "bool-type":
            writer.execute(f'ALTER TABLE {table} ALTER COLUMN "available" TYPE INTEGER')
        else:
            writer.execute(f"UPDATE {sets} SET recorded_at=recorded_at+INTERVAL '1 second'")
            writer.execute(f"UPDATE {table} SET recorded_at=recorded_at+INTERVAL '1 second'")
    finally:
        writer.close()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        with pytest.raises(codec.Rejected):
            silver.read_decision_evidence_silver(reader, **_args(receipt))
    finally:
        reader.close()


def test_failed_review_cannot_heal(tmp_path: Path) -> None:
    path, pins = _bronze(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "silver.duckdb"))
    try:
        silver.initialize_decision_evidence_silver(target)
        with pytest.raises(codec.Rejected, match="REVIEWED_EVIDENCE_CONTEXT_CHANGED"):
            silver.persist_decision_evidence_silver(
                bronze,
                target,
                pins=pins,
                expected_context_sha256="b" * 64,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        changed = replace(pins, envelope_hash="c" * 64, recording_fingerprint="d" * 64)
        assert changed.scope_id == pins.scope_id
        with pytest.raises(codec.Rejected, match="EVIDENCE_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"):
            silver.persist_decision_evidence_silver(
                bronze,
                target,
                pins=changed,
                expected_context_sha256="e" * 64,
                actor_id="other",
                code_revision=REVISION,
            )
    finally:
        target.close()
        bronze.close()


def test_native_source_and_legacy_sql_are_distinct(tmp_path: Path) -> None:
    path, silver_path, pins, receipt = _chain(tmp_path)
    legacy_path = tmp_path / "legacy.duckdb"
    writer = duckdb.connect(str(legacy_path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        writer.execute(f"UPDATE {table} SET available=NOT available")
    finally:
        writer.close()
    legacy = duckdb.connect(str(legacy_path), read_only=True)
    bronze = duckdb.connect(str(path), read_only=True)
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        records = silver.revalidate_decision_evidence_silver(bronze, reader, **_args(receipt))
        assert len(records) == 4
        with pytest.raises(codec.Rejected, match="CURRENT_LEGACY_EVIDENCE_SOURCE_CHANGED"):
            bronze_api.revalidate_decision_evidence_source(legacy, bronze, **pins.reader_args())
    finally:
        reader.close()
        bronze.close()
        legacy.close()
    writer = duckdb.connect(str(path))
    try:
        events = common.name(writer, "medallion_audit", "job_events")
        writer.execute(f"DELETE FROM {events} WHERE state='SUCCEEDED'")
    finally:
        writer.close()
    bronze = duckdb.connect(str(path), read_only=True)
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        assert len(silver.read_decision_evidence_silver(reader, **_args(receipt))) == 4
        with pytest.raises(codec.Rejected, match="ORIGINAL_EVIDENCE_AUDIT_NOT_VERIFIED"):
            silver.revalidate_decision_evidence_silver(bronze, reader, **_args(receipt))
    finally:
        reader.close()
        bronze.close()


def test_partial_insert_rollback_and_original_failure(tmp_path: Path) -> None:
    path, pins = _bronze(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    owner = duckdb.connect(str(tmp_path / "silver.duckdb"))

    class Fail:
        def __init__(self) -> None:
            self.count = 0

        def execute(self, sql: str, parameters: Any = None) -> Any:
            if sql.startswith("INSERT INTO") and '"evidence_observations"' in sql:
                self.count += 1
                if self.count == 2:
                    raise RuntimeError("INJECTED_SECOND_INSERT_FAILURE")
            return owner.execute(sql) if parameters is None else owner.execute(sql, parameters)

    try:
        silver.initialize_decision_evidence_silver(owner)
        context = silver.observe_decision_evidence_bronze(bronze, pins=pins)
        with pytest.raises(RuntimeError, match="INJECTED_SECOND_INSERT_FAILURE"):
            silver.persist_decision_evidence_silver(
                bronze,
                Fail(),
                pins=pins,
                expected_context_sha256=codec.sha(context),
                actor_id="synthetic",
                code_revision=REVISION,
            )
        for table in ("evidence_sets", "evidence_observations", "evidence_attempts"):
            qualified = common.name(owner, "silver", table)
            assert owner.execute(f"SELECT count(*) FROM {qualified}").fetchone() == (0,)
        with pytest.raises(codec.Rejected, match="EVIDENCE_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"):
            silver.persist_decision_evidence_silver(
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


def test_final_audit_failure_blocks_original_read(tmp_path: Path, monkeypatch: Any) -> None:
    path, pins = _bronze(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    silver_path = tmp_path / "silver.duckdb"
    target = duckdb.connect(str(silver_path))
    actual = AuditLedger.transition

    def fail(self: Any, job: str, state: JobState, reason_code: str | None = None) -> None:
        if state == JobState.SUCCEEDED:
            raise RuntimeError("INJECTED_FINAL_AUDIT_FAILURE")
        actual(self, job, state, reason_code)

    try:
        silver.initialize_decision_evidence_silver(target)
        context = silver.observe_decision_evidence_bronze(bronze, pins=pins)
        monkeypatch.setattr(AuditLedger, "transition", fail)
        with pytest.raises(RuntimeError, match="INJECTED_FINAL_AUDIT_FAILURE"):
            silver.persist_decision_evidence_silver(
                bronze,
                target,
                pins=pins,
                expected_context_sha256=codec.sha(context),
                actor_id="synthetic",
                code_revision=REVISION,
            )
        table = common.name(target, "silver", "evidence_sets")
        row = target.execute(f"SELECT revision_id FROM {table}").fetchone()
        assert row is not None
        revision = row[0]
    finally:
        target.close()
        bronze.close()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        with pytest.raises(codec.Rejected, match="ORIGINAL_EVIDENCE_SILVER_AUDIT_NOT_VERIFIED"):
            silver.read_decision_evidence_silver(
                reader, revision_id=revision, expected_recording_fingerprint="b" * 64
            )
    finally:
        reader.close()


def test_alias_initialization_and_hex_predecode(tmp_path: Path) -> None:
    target = duckdb.connect(str(tmp_path / "silver.duckdb"))
    alias = target.cursor()
    pins = silver.EvidenceBronzePins("fixture", "a" * 64, "b" * 64, "c" * 64, "d" * 64)
    try:
        silver.initialize_decision_evidence_silver(target)
        with pytest.raises(codec.Rejected, match="EMPTY_EVIDENCE_SILVER_INITIALIZATION_REQUIRED"):
            silver.initialize_decision_evidence_silver(target)
        with pytest.raises(codec.Rejected, match="SEPARATE_TARGET_REQUIRED"):
            silver.persist_decision_evidence_silver(
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
    raw = codec.canonical(
        dict(
            version=silver.VERSION, pins=asdict(pins), snapshot_hex="z" * (2 * codec.MAX_BYTES + 1)
        )
    )
    with pytest.raises(codec.Rejected, match="SNAPSHOT_HEX_BOUND"):
        silver._derive(raw)


@pytest.mark.parametrize(
    "kind",
    ["contract", "definition", "duplicate-job", "orphan"],
    ids=["contract", "definition", "duplicate-job", "orphan-records"],
)
def test_original_jobs_definitions_and_orphans(tmp_path: Path, kind: str) -> None:
    path, silver_path, pins, receipt = _chain(tmp_path)
    writer = duckdb.connect(str(silver_path))
    try:
        if kind == "contract":
            table = common.name(writer, "medallion_audit", "dataset_contracts")
            writer.execute(f"UPDATE {table} SET fingerprint=?", ["f" * 64])
        elif kind == "definition":
            table = common.name(writer, "silver", "evidence_versions")
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
            for schema, table in (
                ("silver", "evidence_sets"),
                ("silver", "evidence_attempts"),
                ("medallion_audit", "job_events"),
                ("medallion_audit", "jobs"),
            ):
                writer.execute(f"DELETE FROM {common.name(writer, schema, table)}")
    finally:
        writer.close()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        with pytest.raises(codec.Rejected):
            silver.read_decision_evidence_silver(reader, **_args(receipt))
    finally:
        reader.close()
    if kind == "orphan":
        bronze = duckdb.connect(str(path), read_only=True)
        target = duckdb.connect(str(silver_path))
        try:
            context = silver.observe_decision_evidence_bronze(bronze, pins=pins)
            with pytest.raises(
                codec.Rejected, match="EVIDENCE_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"
            ):
                silver.persist_decision_evidence_silver(
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


def test_both_key_constraints_and_scalar_aggregate(tmp_path: Path) -> None:
    _path, silver_path, _pins, receipt = _chain(tmp_path)
    writer = duckdb.connect(str(silver_path))
    try:
        table = common.name(writer, "silver", "evidence_observations")
        with pytest.raises(duckdb.ConstraintException):
            writer.execute(f"UPDATE {table} SET evidence_id='same-id'")
        with pytest.raises(duckdb.ConstraintException):
            writer.execute(
                f"UPDATE {table} SET run_id='R',ts=TIMESTAMP '2026-01-01 09:15:00',"
                "symbol='S',plugin='P'"
            )
        # Unique timestamp fields differ, so natural keys remain distinct under this corruption.
        writer.execute(
            f"UPDATE {table} SET evidence_id=repeat('x',65500) || evidence_id,"
            "run_id=repeat('r',65536),symbol=repeat('s',65536),"
            "plugin=repeat('p',65536),payload_json=repeat('q',65536)"
        )
    finally:
        writer.close()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        with pytest.raises(codec.Rejected, match="EVIDENCE_SILVER_TRANSFER_BOUND"):
            silver.read_decision_evidence_silver(reader, **_args(receipt))
    finally:
        reader.close()


def test_missing_bronze_and_second_observation_drift(tmp_path: Path, monkeypatch: Any) -> None:
    path, silver_path, _pins, receipt = _chain(tmp_path)
    path.unlink()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        assert len(silver.read_decision_evidence_silver(reader, **_args(receipt))) == 4
    finally:
        reader.close()
    other = tmp_path / "new-attempt"
    other.mkdir()
    path, pins = _bronze(other)
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(other / "silver.duckdb"))
    actual = silver.observe_decision_evidence_bronze
    count = 0

    def drift(conn: Any, *, pins: silver.EvidenceBronzePins) -> bytes:
        nonlocal count
        value = actual(conn, pins=pins)
        count += 1
        # Boundary injection after actual source verification, not authentic source drift.
        return value + b" " if count == 2 else value

    try:
        silver.initialize_decision_evidence_silver(target)
        context = actual(bronze, pins=pins)
        monkeypatch.setattr(silver, "observe_decision_evidence_bronze", drift)
        with pytest.raises(codec.Rejected, match="EVIDENCE_BRONZE_CONTEXT_DRIFT"):
            silver.persist_decision_evidence_silver(
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


@pytest.mark.parametrize("text", ["x" * 65536], ids=["maximum-payload-text"])
def test_maximum_payload_actual_native_persistence(tmp_path: Path, text: str) -> None:
    path, pins = _bronze(tmp_path, maximum_payload=text)
    silver_path = tmp_path / "silver.duckdb"
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(silver_path))
    try:
        silver.initialize_decision_evidence_silver(target)
        context = silver.observe_decision_evidence_bronze(bronze, pins=pins)
        receipt = silver.persist_decision_evidence_silver(
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
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        records = silver.read_decision_evidence_silver(reader, **_args(receipt))
        docs = [codec.parse(raw, codec.MAX_RECORD) for raw in records]
        opaque = next(doc for doc in docs if doc["stored_fields"]["evidence_id"] == "opaque")
        assert opaque["stored_fields"]["payload_json"] == text
    finally:
        reader.close()
