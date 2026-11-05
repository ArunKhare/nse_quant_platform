"""Actual legacy builder/writer -> native spot Bronze -> persisted Silver and faults."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import legacy_daily_rv_bronze as common
from nse_quant.data_platform import legacy_spot_feature_bronze as bronze_api
from nse_quant.data_platform import legacy_spot_feature_silver_store as silver
from nse_quant.data_platform import legacy_spot_features as codec
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.features.spot_features import SpotFeatureBuilder
from nse_quant.persistence.duckdb_store import DuckDBStore

AT = datetime(2026, 1, 1, tzinfo=UTC)
REVISION = "a" * 40


def _bronze(tmp_path: Path) -> tuple[Path, silver.SpotBronzePins]:
    legacy_path = tmp_path / "legacy.duckdb"
    bronze_path = tmp_path / "bronze.duckdb"
    legacy = DuckDBStore(path=legacy_path)
    try:
        candles = [
            dict(
                date=AT + timedelta(minutes=i),
                open=100.0 + i,
                high=102.0 + i,
                low=99.0 + i,
                close=101.0 + i,
                volume=100 + i,
                oi=0,
            )
            for i in range(40)
        ]
        assert legacy.write_spot_candles(candles, "NIFTY", 256265, "1m") == 40
        frame = SpotFeatureBuilder(legacy).build("NIFTY")
        assert legacy.write_spot_features(frame) == 40
        replacement = frame.iloc[:1].copy()
        # Deliberate boundary replacement, not recomputed builder output.
        replacement["close"] = -0.0
        assert legacy.write_spot_features(replacement) == 1
    finally:
        legacy.close()
    source = duckdb.connect(str(legacy_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = bronze_api.capture_spot_features(source, source_label="fixture")
        receipt = bronze_api.preserve_spot_features(
            source,
            target,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
        pins = silver.SpotBronzePins(
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


def _chain(tmp_path: Path) -> tuple[Path, Path, silver.SpotBronzePins, dict[str, Any]]:
    path, pins = _bronze(tmp_path)
    silver_path = tmp_path / "silver.duckdb"  # Keep actual catalog/schema collision.
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(silver_path))
    try:
        silver.initialize_spot_feature_silver(target)
        context = silver.observe_spot_feature_bronze(bronze, pins=pins)
        receipt = silver.persist_spot_feature_silver(
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


def test_actual_native_producer_all_field_replay_and_current_upstream(tmp_path: Path) -> None:
    path, silver_path, pins, receipt = _chain(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        records = silver.read_spot_feature_silver(reader, **_args(receipt))
        assert records == bronze_api.read_spot_feature_bronze(bronze, **pins.reader_args())
        assert records == silver.revalidate_spot_feature_silver(bronze, reader, **_args(receipt))
        assert len(records) == 40
        columns = ",".join('"' + n + '"' for n in codec.NAMES)
        table = common.name(reader, "silver", "spot_observations")
        stored = reader.execute(f"SELECT {columns} FROM {table} ORDER BY ordinal").fetchall()
        for ordinal, (row, raw) in enumerate(zip(stored, records, strict=True)):
            doc = codec.parse(raw, codec.MAX_RECORD)
            assert row == silver._values(raw)[2:]
            assert doc["source_ordinal"] == ordinal
            assert doc["native_features_recomputed"] is False
            assert doc["analytical_assumptions_verified"] is False
            assert doc["authoritative_market_coverage_verified"] is False
            assert doc["original_availability_at"] is None
            assert doc["decision_eligibility_asserted"] is False
        first = codec.parse(records[0], codec.MAX_RECORD)["stored_fields"]
        assert first["close"] == (-0.0).hex()
        assert first["return_1m"] is None
        assert first["rv_1m_30"] is None
        assert first["trend_60m"] is None
    finally:
        reader.close()
        bronze.close()


@pytest.mark.parametrize("field,kind", codec.SCHEMA, ids=[n for n, _ in codec.SCHEMA])
def test_all_15_materialized_fields_are_reconciled(tmp_path: Path, field: str, kind: str) -> None:
    _path, silver_path, _pins, receipt = _chain(tmp_path)
    writer = duckdb.connect(str(silver_path))
    try:
        table = common.name(writer, "silver", "spot_observations")
        value: object = (
            AT + timedelta(days=1)
            if kind == "TIMESTAMP WITH TIME ZONE"
            else ("changed-symbol" if kind == "VARCHAR" else (9.5).hex())
        )
        writer.execute(f'UPDATE {table} SET "{field}"=? WHERE ordinal=0', [value])
    finally:
        writer.close()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        with pytest.raises(codec.Rejected, match="SPOT_SILVER_FULL_RECORD_RECOMPUTATION_MISMATCH"):
            silver.read_spot_feature_silver(reader, **_args(receipt))
    finally:
        reader.close()


@pytest.mark.parametrize(
    "kind",
    [
        "bytes",
        "missing",
        "ordinal",
        "context",
        "record-bound",
        "aggregate",
        "nullable-mask",
        "link",
        "audit",
        "clock",
    ],
    ids=[
        "bytes",
        "missing",
        "ordinal",
        "context",
        "record-bound",
        "aggregate",
        "nullable-mask",
        "link",
        "audit",
        "clock",
    ],
)
def test_original_recording_faults(tmp_path: Path, kind: str) -> None:
    _path, silver_path, _pins, receipt = _chain(tmp_path)
    writer = duckdb.connect(str(silver_path))
    try:
        records = common.name(writer, "silver", "spot_observations")
        sets = common.name(writer, "silver", "spot_sets")
        if kind == "bytes":
            writer.execute(f"UPDATE {records} SET record_bytes=? WHERE ordinal=0", [b"{}"])
        elif kind == "missing":
            writer.execute(f"DELETE FROM {records} WHERE ordinal=0")
        elif kind == "ordinal":
            writer.execute(f"UPDATE {records} SET ordinal=99 WHERE ordinal=0")
        elif kind == "context":
            writer.execute(f"UPDATE {sets} SET context=?", [b"x" * (silver.MAX_CONTEXT + 1)])
        elif kind in ("record-bound", "aggregate"):
            bound = codec.MAX_RECORD if kind == "record-bound" else codec.MAX_RECORDS
            writer.execute(
                f"UPDATE {records} SET record_bytes=? WHERE ordinal=0", [b"x" * (bound + 1)]
            )
        elif kind == "nullable-mask":
            writer.execute(f"UPDATE {records} SET return_1m=? WHERE ordinal=0", ["x" * 65])
        elif kind == "link":
            writer.execute(f"DELETE FROM {common.name(writer, 'silver', 'spot_attempts')}")
        elif kind == "audit":
            events = common.name(writer, "medallion_audit", "job_events")
            writer.execute(f"DELETE FROM {events} WHERE state='SUCCEEDED'")
        else:
            writer.execute(f"UPDATE {sets} SET recorded_at=recorded_at+INTERVAL '1 second'")
            writer.execute(f"UPDATE {records} SET recorded_at=recorded_at+INTERVAL '1 second'")
    finally:
        writer.close()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        with pytest.raises(codec.Rejected):
            silver.read_spot_feature_silver(reader, **_args(receipt))
    finally:
        reader.close()


def test_failed_review_cannot_heal_with_new_recording_pins(tmp_path: Path) -> None:
    path, pins = _bronze(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "silver.duckdb"))
    try:
        silver.initialize_spot_feature_silver(target)
        with pytest.raises(codec.Rejected, match="REVIEWED_SPOT_CONTEXT_CHANGED"):
            silver.persist_spot_feature_silver(
                bronze,
                target,
                pins=pins,
                expected_context_sha256="b" * 64,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        changed = replace(pins, envelope_hash="c" * 64, recording_fingerprint="d" * 64)
        assert changed.scope_id == pins.scope_id
        with pytest.raises(codec.Rejected, match="SPOT_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"):
            silver.persist_spot_feature_silver(
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


def test_bronze_audit_change_only_blocks_current_native_check(tmp_path: Path) -> None:
    path, silver_path, _pins, receipt = _chain(tmp_path)
    writer = duckdb.connect(str(path))
    try:
        events = common.name(writer, "medallion_audit", "job_events")
        writer.execute(f"DELETE FROM {events} WHERE state='SUCCEEDED'")
    finally:
        writer.close()
    bronze = duckdb.connect(str(path), read_only=True)
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        assert len(silver.read_spot_feature_silver(reader, **_args(receipt))) == 40
        with pytest.raises(codec.Rejected, match="ORIGINAL_SPOT_AUDIT_NOT_VERIFIED"):
            silver.revalidate_spot_feature_silver(bronze, reader, **_args(receipt))
    finally:
        reader.close()
        bronze.close()


def test_retained_read_does_not_require_bronze_file(tmp_path: Path) -> None:
    path, silver_path, _pins, receipt = _chain(tmp_path)
    path.unlink()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        assert len(silver.read_spot_feature_silver(reader, **_args(receipt))) == 40
    finally:
        reader.close()


def test_partial_second_insert_rolls_back_without_healing(tmp_path: Path) -> None:
    path, pins = _bronze(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    owner = duckdb.connect(str(tmp_path / "silver.duckdb"))

    class Fail:
        def __init__(self) -> None:
            self.count = 0

        def execute(self, sql: str, parameters: Any = None) -> Any:
            if sql.startswith("INSERT INTO") and '"spot_observations"' in sql:
                self.count += 1
                if self.count == 2:
                    raise RuntimeError("INJECTED_SECOND_INSERT_FAILURE")
            return owner.execute(sql) if parameters is None else owner.execute(sql, parameters)

    try:
        silver.initialize_spot_feature_silver(owner)
        context = silver.observe_spot_feature_bronze(bronze, pins=pins)
        with pytest.raises(RuntimeError, match="INJECTED_SECOND_INSERT_FAILURE"):
            silver.persist_spot_feature_silver(
                bronze,
                Fail(),
                pins=pins,
                expected_context_sha256=codec.sha(context),
                actor_id="synthetic",
                code_revision=REVISION,
            )
        for table in ("spot_sets", "spot_observations", "spot_attempts"):
            qualified = common.name(owner, "silver", table)
            assert owner.execute(f"SELECT count(*) FROM {qualified}").fetchone() == (0,)
        with pytest.raises(codec.Rejected, match="SPOT_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"):
            silver.persist_spot_feature_silver(
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


def test_final_audit_failure_leaves_original_unreadable(tmp_path: Path, monkeypatch: Any) -> None:
    path, pins = _bronze(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    target_path = tmp_path / "silver.duckdb"
    target = duckdb.connect(str(target_path))
    actual = AuditLedger.transition

    def fail(self: Any, job: str, state: JobState, reason_code: str | None = None) -> None:
        if state == JobState.SUCCEEDED:
            raise RuntimeError("INJECTED_FINAL_AUDIT_FAILURE")
        actual(self, job, state, reason_code)

    try:
        silver.initialize_spot_feature_silver(target)
        context = silver.observe_spot_feature_bronze(bronze, pins=pins)
        monkeypatch.setattr(AuditLedger, "transition", fail)
        with pytest.raises(RuntimeError, match="INJECTED_FINAL_AUDIT_FAILURE"):
            silver.persist_spot_feature_silver(
                bronze,
                target,
                pins=pins,
                expected_context_sha256=codec.sha(context),
                actor_id="synthetic",
                code_revision=REVISION,
            )
        table = common.name(target, "silver", "spot_sets")
        row = target.execute(f"SELECT revision_id FROM {table}").fetchone()
        assert row is not None
        revision = row[0]
        with pytest.raises(codec.Rejected, match="SPOT_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"):
            silver.persist_spot_feature_silver(
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
        with pytest.raises(codec.Rejected, match="ORIGINAL_SPOT_SILVER_AUDIT_NOT_VERIFIED"):
            silver.read_spot_feature_silver(
                reader, revision_id=revision, expected_recording_fingerprint="b" * 64
            )
    finally:
        reader.close()


def test_second_actual_observation_then_injected_drift(tmp_path: Path, monkeypatch: Any) -> None:
    path, pins = _bronze(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "silver.duckdb"))
    actual = silver.observe_spot_feature_bronze
    count = 0

    def drift(conn: Any, *, pins: silver.SpotBronzePins) -> bytes:
        nonlocal count
        context = actual(conn, pins=pins)
        count += 1
        # Negative boundary after a real original-source read, not authentic source drift.
        return context + b" " if count == 2 else context

    try:
        silver.initialize_spot_feature_silver(target)
        context = actual(bronze, pins=pins)
        monkeypatch.setattr(silver, "observe_spot_feature_bronze", drift)
        with pytest.raises(codec.Rejected, match="SPOT_BRONZE_CONTEXT_DRIFT"):
            silver.persist_spot_feature_silver(
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


def test_alias_init_and_hex_predecode(tmp_path: Path) -> None:
    target = duckdb.connect(str(tmp_path / "silver.duckdb"))
    alias = target.cursor()
    pins = silver.SpotBronzePins("fixture", "a" * 64, "b" * 64, "c" * 64, "d" * 64)
    try:
        silver.initialize_spot_feature_silver(target)
        with pytest.raises(codec.Rejected, match="EMPTY_SPOT_SILVER_INITIALIZATION_REQUIRED"):
            silver.initialize_spot_feature_silver(target)
        with pytest.raises(codec.Rejected, match="SEPARATE_TARGET_REQUIRED"):
            silver.persist_spot_feature_silver(
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
    context = codec.canonical(
        dict(
            version=silver.VERSION, pins=asdict(pins), snapshot_hex="z" * (2 * codec.MAX_BYTES + 1)
        )
    )
    with pytest.raises(codec.Rejected, match="SNAPSHOT_HEX_BOUND"):
        silver._derive(context)


@pytest.mark.parametrize(
    "kind",
    ["contract", "definition", "duplicate-job", "orphan"],
    ids=["contract", "definition", "duplicate-job", "orphan-records"],
)
def test_original_contract_jobs_and_orphans(tmp_path: Path, kind: str) -> None:
    path, silver_path, pins, receipt = _chain(tmp_path)
    writer = duckdb.connect(str(silver_path))
    try:
        if kind == "contract":
            table = common.name(writer, "medallion_audit", "dataset_contracts")
            writer.execute(f"UPDATE {table} SET fingerprint=?", ["f" * 64])
        elif kind == "definition":
            table = common.name(writer, "silver", "spot_versions")
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
                ("silver", "spot_sets"),
                ("silver", "spot_attempts"),
                ("medallion_audit", "job_events"),
                ("medallion_audit", "jobs"),
            ):
                writer.execute(f"DELETE FROM {common.name(writer, schema, table)}")
    finally:
        writer.close()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        with pytest.raises(codec.Rejected):
            silver.read_spot_feature_silver(reader, **_args(receipt))
    finally:
        reader.close()
    if kind == "orphan":
        bronze = duckdb.connect(str(path), read_only=True)
        target = duckdb.connect(str(silver_path))
        try:
            context = silver.observe_spot_feature_bronze(bronze, pins=pins)
            with pytest.raises(codec.Rejected, match="SPOT_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"):
                silver.persist_spot_feature_silver(
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
def test_maximum_symbol_persists_with_actual_native_source(tmp_path: Path, symbol: str) -> None:
    legacy_path = tmp_path / "legacy.duckdb"
    bronze_path = tmp_path / "bronze.duckdb"
    silver_path = tmp_path / "silver.duckdb"
    writer = duckdb.connect(str(legacy_path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        columns = ",".join(f'"{n}" {k}' for n, k in codec.SCHEMA)
        writer.execute(f'CREATE TABLE {table} ({columns},PRIMARY KEY("symbol","ts"))')
        writer.execute(f"INSERT INTO {table} (symbol,ts,close) VALUES (?,?,?)", [symbol, AT, -0.0])
    finally:
        writer.close()
    source = duckdb.connect(str(legacy_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = bronze_api.capture_spot_features(source, source_label="maximum")
        receipt = bronze_api.preserve_spot_features(
            source,
            target,
            source_label="maximum",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
        pins = silver.SpotBronzePins(
            "maximum",
            receipt["snapshot_id"],
            receipt["capture_event_id"],
            receipt["envelope_hash"],
            receipt["recording_fingerprint"],
        )
    finally:
        target.close()
        source.close()
    bronze = duckdb.connect(str(bronze_path), read_only=True)
    target = duckdb.connect(str(silver_path))
    try:
        silver.initialize_spot_feature_silver(target)
        context = silver.observe_spot_feature_bronze(bronze, pins=pins)
        result = silver.persist_spot_feature_silver(
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
        records = silver.read_spot_feature_silver(reader, **_args(result))
        doc = codec.parse(records[0], codec.MAX_RECORD)
        assert doc["stored_fields"]["symbol"] == symbol
        assert doc["stored_fields"]["close"] == (-0.0).hex()
    finally:
        reader.close()


def test_current_legacy_sql_is_not_current_native_upstream(tmp_path: Path) -> None:
    path, silver_path, pins, receipt = _chain(tmp_path)
    legacy_path = tmp_path / "legacy.duckdb"
    writer = duckdb.connect(str(legacy_path))
    try:
        writer.execute(f"UPDATE {common.name(writer, 'main', codec.TABLE)} SET return_1m=0.9")
    finally:
        writer.close()
    legacy = duckdb.connect(str(legacy_path), read_only=True)
    bronze = duckdb.connect(str(path), read_only=True)
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        assert len(silver.revalidate_spot_feature_silver(bronze, reader, **_args(receipt))) == 40
        with pytest.raises(codec.Rejected, match="CURRENT_LEGACY_SPOT_SOURCE_CHANGED"):
            bronze_api.revalidate_spot_feature_source(legacy, bronze, **pins.reader_args())
    finally:
        reader.close()
        bronze.close()
        legacy.close()
