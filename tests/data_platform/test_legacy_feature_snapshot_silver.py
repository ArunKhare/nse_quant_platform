"""Actual legacy writer/native Bronze -> persisted feature Silver integration and faults."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.core.models import MarketFeatures
from nse_quant.data_platform import legacy_daily_rv_bronze as common
from nse_quant.data_platform import legacy_feature_snapshot_bronze as bronze_api
from nse_quant.data_platform import legacy_feature_snapshot_silver_store as silver
from nse_quant.data_platform import legacy_feature_snapshots as codec
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.features.feature_store import FeatureStore

AT = datetime(2026, 1, 1, tzinfo=UTC)
REVISION = "a" * 40
DIAGNOSTICS = '{ "eligible":true, "eligible":false, "availability_verified":true }'


def _bronze(tmp_path: Path) -> tuple[Path, silver.FeatureBronzePins]:
    legacy_path = tmp_path / "legacy.duckdb"
    bronze_path = tmp_path / "bronze.duckdb"
    writer = duckdb.connect(str(legacy_path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        columns = ",".join(f'"{n}" {k}' for n, k in codec.SCHEMA)
        writer.execute(f'CREATE TABLE {table} ({columns},PRIMARY KEY("feature_id"))')
        legacy = FeatureStore(writer)
        features = MarketFeatures(
            ts=AT.astimezone(timezone(timedelta(hours=5, minutes=30))),
            underlying="NIFTY",
            expiry=date(2026, 1, 29),
            spot=-0.0,
            total_call_oi=0,
            total_put_oi=2**63 - 1,
            diagnostics={"retained": True},
        )
        legacy.save("overwritten", features)
        legacy.save("retained", features)
        legacy.save(
            "second",
            MarketFeatures(
                ts=AT + timedelta(seconds=1),
                underlying="BANK",
                expiry=date(2026, 1, 29),
                spot=25000.0,
                iv_rv_spread=-0.1,
            ),
        )
        writer.execute(f"UPDATE {table} SET diagnostics=? WHERE run_id='retained'", [DIAGNOSTICS])
        writer.execute(f"INSERT INTO {table} (feature_id) VALUES ('opaque-null-row')")
    finally:
        writer.close()
    source = duckdb.connect(str(legacy_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = bronze_api.capture_feature_snapshots(source, source_label="fixture")
        receipt = bronze_api.preserve_feature_snapshots(
            source,
            target,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
        pins = silver.FeatureBronzePins(
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


def _chain(tmp_path: Path) -> tuple[Path, Path, silver.FeatureBronzePins, dict[str, Any]]:
    path, pins = _bronze(tmp_path)
    silver_path = tmp_path / "silver.duckdb"  # Keep actual catalog/schema collision.
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(silver_path))
    try:
        silver.initialize_feature_snapshot_silver(target)
        context = silver.observe_feature_snapshot_bronze(bronze, pins=pins)
        receipt = silver.persist_feature_snapshot_silver(
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


def test_actual_native_producer_and_all_field_replay(tmp_path: Path) -> None:
    path, silver_path, pins, receipt = _chain(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        records = silver.read_feature_snapshot_silver(reader, **_args(receipt))
        assert records == bronze_api.read_feature_snapshot_bronze(bronze, **pins.reader_args())
        assert records == silver.revalidate_feature_snapshot_silver(
            bronze, reader, **_args(receipt)
        )
        assert len(records) == 3
        docs = [codec.parse(r, codec.MAX_RECORD) for r in records]
        by_run = {d["stored_fields"]["run_id"]: d["stored_fields"] for d in docs}
        assert by_run["retained"]["feature_id"].endswith("+05:30")
        assert by_run["retained"]["ts"] == AT.isoformat()
        assert by_run["retained"]["spot"] == (-0.0).hex()
        assert by_run["retained"]["total_call_oi"] == "0"
        assert by_run["retained"]["total_put_oi"] == str(2**63 - 1)
        assert by_run["retained"]["diagnostics"] == DIAGNOSTICS
        assert by_run["second"]["iv_rv_spread"] == (-0.1).hex()
        assert all(v is None for k, v in by_run[None].items() if k != "feature_id")
        for doc in docs:
            assert doc["diagnostics_interpreted"] is False
            assert doc["native_features_recomputed"] is False
            assert doc["decision_eligibility_asserted"] is False
        table = common.name(reader, "silver", "feature_observations")
        columns = ",".join(f'"{n}"' for n, _ in codec.SCHEMA)
        stored = reader.execute(f"SELECT {columns} FROM {table} ORDER BY ordinal").fetchall()
        for row, raw in zip(stored, records, strict=True):
            assert row == silver._values(raw)[2:]
    finally:
        reader.close()
        bronze.close()


@pytest.mark.parametrize("field,kind", codec.SCHEMA, ids=[n for n, _ in codec.SCHEMA])
def test_every_materialized_field_is_reconciled(tmp_path: Path, field: str, kind: str) -> None:
    _path, silver_path, _pins, receipt = _chain(tmp_path)
    writer = duckdb.connect(str(silver_path))
    try:
        table = common.name(writer, "silver", "feature_observations")
        if kind == "TIMESTAMP WITH TIME ZONE":
            value: object = AT + timedelta(days=1)
        elif kind == "DATE":
            value = date(2026, 2, 1)
        elif kind == "BIGINT":
            value = -123
        elif kind == "DOUBLE":
            value = (9.5).hex()
        else:
            value = '{"tampered":true}' if kind == "JSON" else "tampered-field"
        writer.execute(f'UPDATE {table} SET "{field}"=? WHERE ordinal=0', [value])
    finally:
        writer.close()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        with pytest.raises(
            codec.Rejected, match="FEATURE_SILVER_FULL_RECORD_RECOMPUTATION_MISMATCH"
        ):
            silver.read_feature_snapshot_silver(reader, **_args(receipt))
    finally:
        reader.close()


@pytest.mark.parametrize(
    "kind",
    [
        "bytes",
        "missing",
        "ordinal",
        "context",
        "record-limit",
        "aggregate",
        "scalar-null-mask",
        "link",
        "audit",
        "clock",
    ],
    ids=[
        "bytes",
        "missing",
        "ordinal",
        "context",
        "record-limit",
        "aggregate",
        "scalar-null-mask",
        "link",
        "audit",
        "clock",
    ],
)
def test_recording_faults(tmp_path: Path, kind: str) -> None:
    _path, silver_path, _pins, receipt = _chain(tmp_path)
    writer = duckdb.connect(str(silver_path))
    try:
        table = common.name(writer, "silver", "feature_observations")
        sets = common.name(writer, "silver", "feature_sets")
        if kind == "bytes":
            writer.execute(f"UPDATE {table} SET record_bytes=? WHERE ordinal=0", [b"{}"])
        elif kind == "missing":
            writer.execute(f"DELETE FROM {table} WHERE ordinal=0")
        elif kind == "ordinal":
            writer.execute(f"UPDATE {table} SET ordinal=99 WHERE ordinal=0")
        elif kind == "context":
            writer.execute(f"UPDATE {sets} SET context=?", [b"x" * (silver.MAX_CONTEXT + 1)])
        elif kind in ("record-limit", "aggregate"):
            bound = codec.MAX_RECORD if kind == "record-limit" else codec.MAX_RECORDS
            writer.execute(
                f"UPDATE {table} SET record_bytes=? WHERE ordinal=0", [b"x" * (bound + 1)]
            )
        elif kind == "scalar-null-mask":
            writer.execute(
                f"UPDATE {table} SET run_id=? WHERE feature_id='opaque-null-row'",
                ["x" * (codec.MAX_CELL + 1)],
            )
        elif kind == "link":
            writer.execute(f"DELETE FROM {common.name(writer, 'silver', 'feature_attempts')}")
        elif kind == "audit":
            events = common.name(writer, "medallion_audit", "job_events")
            writer.execute(f"DELETE FROM {events} WHERE state='SUCCEEDED'")
        else:
            writer.execute(f"UPDATE {sets} SET recorded_at=recorded_at+INTERVAL '1 second'")
            writer.execute(f"UPDATE {table} SET recorded_at=recorded_at+INTERVAL '1 second'")
    finally:
        writer.close()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        with pytest.raises(codec.Rejected):
            silver.read_feature_snapshot_silver(reader, **_args(receipt))
    finally:
        reader.close()


def test_failed_context_review_cannot_heal_with_new_pins(tmp_path: Path) -> None:
    path, pins = _bronze(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "silver.duckdb"))
    try:
        silver.initialize_feature_snapshot_silver(target)
        with pytest.raises(codec.Rejected, match="REVIEWED_FEATURE_CONTEXT_CHANGED"):
            silver.persist_feature_snapshot_silver(
                bronze,
                target,
                pins=pins,
                expected_context_sha256="b" * 64,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        changed = replace(pins, envelope_hash="c" * 64, recording_fingerprint="d" * 64)
        assert changed.scope_id == pins.scope_id
        with pytest.raises(codec.Rejected, match="FEATURE_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"):
            silver.persist_feature_snapshot_silver(
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


def test_current_bronze_failure_distinct_from_retained_silver(tmp_path: Path) -> None:
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
        assert len(silver.read_feature_snapshot_silver(reader, **_args(receipt))) == 3
        with pytest.raises(codec.Rejected, match="ORIGINAL_FEATURE_AUDIT_NOT_VERIFIED"):
            silver.revalidate_feature_snapshot_silver(bronze, reader, **_args(receipt))
    finally:
        reader.close()
        bronze.close()


def test_partial_sql_rollback_leaves_original_failure(tmp_path: Path) -> None:
    path, pins = _bronze(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    owner = duckdb.connect(str(tmp_path / "silver.duckdb"))

    class Fail:
        def __init__(self) -> None:
            self.count = 0

        def execute(self, sql: str, parameters: Any = None) -> Any:
            if sql.startswith("INSERT INTO") and '"feature_observations"' in sql:
                self.count += 1
                if self.count == 2:
                    raise RuntimeError("INJECTED_SECOND_INSERT_FAILURE")
            return owner.execute(sql) if parameters is None else owner.execute(sql, parameters)

    try:
        silver.initialize_feature_snapshot_silver(owner)
        context = silver.observe_feature_snapshot_bronze(bronze, pins=pins)
        with pytest.raises(RuntimeError, match="INJECTED_SECOND_INSERT_FAILURE"):
            silver.persist_feature_snapshot_silver(
                bronze,
                Fail(),
                pins=pins,
                expected_context_sha256=codec.sha(context),
                actor_id="synthetic",
                code_revision=REVISION,
            )
        for table in ("feature_sets", "feature_observations", "feature_attempts"):
            qualified = common.name(owner, "silver", table)
            assert owner.execute(f"SELECT count(*) FROM {qualified}").fetchone() == (0,)
        with pytest.raises(codec.Rejected, match="FEATURE_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"):
            silver.persist_feature_snapshot_silver(
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
    target_path = tmp_path / "silver.duckdb"
    target = duckdb.connect(str(target_path))
    actual = AuditLedger.transition

    def fail(self: Any, job: str, state: JobState, reason_code: str | None = None) -> None:
        if state == JobState.SUCCEEDED:
            raise RuntimeError("INJECTED_FINAL_AUDIT_FAILURE")
        actual(self, job, state, reason_code)

    try:
        silver.initialize_feature_snapshot_silver(target)
        context = silver.observe_feature_snapshot_bronze(bronze, pins=pins)
        monkeypatch.setattr(AuditLedger, "transition", fail)
        with pytest.raises(RuntimeError, match="INJECTED_FINAL_AUDIT_FAILURE"):
            silver.persist_feature_snapshot_silver(
                bronze,
                target,
                pins=pins,
                expected_context_sha256=codec.sha(context),
                actor_id="synthetic",
                code_revision=REVISION,
            )
        table = common.name(target, "silver", "feature_sets")
        row = target.execute(f"SELECT revision_id FROM {table}").fetchone()
        assert row is not None
        revision = row[0]
        with pytest.raises(codec.Rejected, match="FEATURE_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"):
            silver.persist_feature_snapshot_silver(
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
        with pytest.raises(codec.Rejected, match="ORIGINAL_FEATURE_SILVER_AUDIT_NOT_VERIFIED"):
            silver.read_feature_snapshot_silver(
                reader, revision_id=revision, expected_recording_fingerprint="b" * 64
            )
    finally:
        reader.close()


def test_second_actual_observation_then_injected_drift(tmp_path: Path, monkeypatch: Any) -> None:
    path, pins = _bronze(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "silver.duckdb"))
    actual = silver.observe_feature_snapshot_bronze
    count = 0

    def drift(conn: Any, *, pins: silver.FeatureBronzePins) -> bytes:
        nonlocal count
        value = actual(conn, pins=pins)
        count += 1
        # Negative boundary after a real native read, not authentic source drift.
        return value + b" " if count == 2 else value

    try:
        silver.initialize_feature_snapshot_silver(target)
        reviewed = actual(bronze, pins=pins)
        monkeypatch.setattr(silver, "observe_feature_snapshot_bronze", drift)
        with pytest.raises(codec.Rejected, match="FEATURE_BRONZE_CONTEXT_DRIFT"):
            silver.persist_feature_snapshot_silver(
                bronze,
                target,
                pins=pins,
                expected_context_sha256=codec.sha(reviewed),
                actor_id="synthetic",
                code_revision=REVISION,
            )
    finally:
        target.close()
        bronze.close()


def test_aliases_initialization_and_hex_predecode(tmp_path: Path) -> None:
    target = duckdb.connect(str(tmp_path / "silver.duckdb"))
    alias = target.cursor()
    pins = silver.FeatureBronzePins("fixture", "a" * 64, "b" * 64, "c" * 64, "d" * 64)
    try:
        silver.initialize_feature_snapshot_silver(target)
        with pytest.raises(codec.Rejected, match="EMPTY_FEATURE_SILVER_INITIALIZATION_REQUIRED"):
            silver.initialize_feature_snapshot_silver(target)
        with pytest.raises(codec.Rejected, match="SEPARATE_TARGET_REQUIRED"):
            silver.persist_feature_snapshot_silver(
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
def test_original_definitions_jobs_and_orphans(tmp_path: Path, kind: str) -> None:
    path, silver_path, pins, receipt = _chain(tmp_path)
    writer = duckdb.connect(str(silver_path))
    try:
        if kind == "contract":
            table = common.name(writer, "medallion_audit", "dataset_contracts")
            writer.execute(f"UPDATE {table} SET fingerprint=?", ["f" * 64])
        elif kind == "definition":
            table = common.name(writer, "silver", "feature_versions")
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
                ("silver", "feature_sets"),
                ("silver", "feature_attempts"),
                ("medallion_audit", "job_events"),
                ("medallion_audit", "jobs"),
            ):
                writer.execute(f"DELETE FROM {common.name(writer, schema, table)}")
    finally:
        writer.close()
    if kind == "orphan":
        bronze = duckdb.connect(str(path), read_only=True)
        target = duckdb.connect(str(silver_path))
        try:
            context = silver.observe_feature_snapshot_bronze(bronze, pins=pins)
            with pytest.raises(
                codec.Rejected, match="FEATURE_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"
            ):
                silver.persist_feature_snapshot_silver(
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
    else:
        reader = duckdb.connect(str(silver_path), read_only=True)
        try:
            with pytest.raises(codec.Rejected):
                silver.read_feature_snapshot_silver(reader, **_args(receipt))
        finally:
            reader.close()


def test_retained_replay_does_not_require_bronze_file(tmp_path: Path) -> None:
    path, silver_path, _pins, receipt = _chain(tmp_path)
    path.unlink()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        assert len(silver.read_feature_snapshot_silver(reader, **_args(receipt))) == 3
    finally:
        reader.close()


@pytest.mark.parametrize("text", ["x" * 65536], ids=["maximum-retained-text"])
def test_maximum_source_text_projection_scalar_boundary(tmp_path: Path, text: str) -> None:
    path, pins = _bronze(tmp_path)
    # Existing source's supported row shape is exercised independently at the scalar boundary.
    row = ["opaque", *([None] * (len(codec.SCHEMA) - 1))]
    row[2] = text
    snapshot = codec.make_snapshot("fixture", [row])
    records = codec.derive_records(
        snapshot.payload,
        snapshot_id=snapshot.snapshot_id,
        capture_event_id=pins.capture_event_id,
        envelope_hash=pins.envelope_hash,
    )
    assert silver._values(records[0])[4] == text
    assert path.exists()
