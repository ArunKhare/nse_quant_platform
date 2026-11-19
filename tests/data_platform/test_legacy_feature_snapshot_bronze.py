"""Actual legacy FeatureStore writer -> native Bronze/audit -> exact typed projections."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.core.models import MarketFeatures
from nse_quant.data_platform import legacy_daily_rv_bronze as common
from nse_quant.data_platform import legacy_feature_snapshot_bronze as native
from nse_quant.data_platform import legacy_feature_snapshots as codec
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.features.feature_store import FeatureStore

AT = datetime(2026, 1, 1, tzinfo=UTC)
REVISION = "a" * 40


def _source(path: Path) -> None:
    writer = duckdb.connect(str(path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        columns = ",".join(f'"{n}" {k}' for n, k in codec.SCHEMA)
        writer.execute(f'CREATE TABLE {table} ({columns},PRIMARY KEY("feature_id"))')
        legacy = FeatureStore(writer)
        local = AT.astimezone(timezone(timedelta(hours=5, minutes=30)))
        features = MarketFeatures(
            ts=local,
            underlying="NIFTY",
            expiry=date(2026, 1, 29),
            spot=-0.0,
            atm_iv=0.25,
            total_call_oi=0,
            diagnostics={"unknown_retained": [1, None], "clock_label": AT},
        )
        legacy.save("superseded-run", features)
        legacy.save("retained-run", features)
        legacy.save(
            "other-run",
            MarketFeatures(
                ts=AT + timedelta(seconds=1),
                underlying="NIFTY",
                expiry=date(2026, 1, 29),
                spot=25000.0,
                iv_rv_spread=-0.1,
                total_put_oi=2**63 - 1,
                diagnostics={},
            ),
        )
    finally:
        writer.close()


def _record(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    legacy_path = tmp_path / "legacy.duckdb"
    bronze_path = tmp_path / "bronze.duckdb"
    _source(legacy_path)
    source = duckdb.connect(str(legacy_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = native.capture_feature_snapshots(source, source_label="fixture")
        receipt = native.preserve_feature_snapshots(
            source,
            target,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
    finally:
        target.close()
        source.close()
    return legacy_path, bronze_path, receipt


def _args(receipt: dict[str, Any]) -> dict[str, str]:
    return dict(
        source_label=receipt["source_label"],
        snapshot_id=receipt["snapshot_id"],
        capture_event_id=receipt["capture_event_id"],
        envelope_hash=receipt["envelope_hash"],
        expected_recording_fingerprint=receipt["recording_fingerprint"],
    )


def test_actual_legacy_writer_native_producer_and_reader(tmp_path: Path) -> None:
    legacy_path, bronze_path, receipt = _record(tmp_path)
    source = duckdb.connect(str(legacy_path), read_only=True)
    bronze = duckdb.connect(str(bronze_path), read_only=True)
    try:
        records = native.read_feature_snapshot_bronze(bronze, **_args(receipt))
        assert records == native.revalidate_feature_snapshot_source(
            source, bronze, **_args(receipt)
        )
        assert len(records) == 2  # actual writer overwrote the same stored key
        docs = [codec.parse(r, codec.MAX_RECORD) for r in records]
        by_run = {d["stored_fields"]["run_id"]: d for d in docs}
        first = by_run["retained-run"]["stored_fields"]
        assert first["feature_id"].endswith("+05:30")
        assert first["ts"] == AT.isoformat()
        assert first["spot"] == (-0.0).hex()
        assert first["total_call_oi"] == "0"
        assert first["total_put_oi"] is None
        assert by_run["other-run"]["stored_fields"]["total_put_oi"] == str(2**63 - 1)
        assert by_run["other-run"]["stored_fields"]["iv_rv_spread"] == (-0.1).hex()
        table = common.name(source, "main", codec.TABLE)
        originals = source.execute(f"SELECT feature_id,CAST(diagnostics AS VARCHAR) FROM {table}")
        exact = dict(originals.fetchall())
        for doc in docs:
            fields = doc["stored_fields"]
            assert fields["diagnostics"] == exact[fields["feature_id"]]
            assert doc["diagnostics_interpreted"] is False
            assert doc["native_features_recomputed"] is False
            assert doc["decision_eligibility_asserted"] is False
            assert doc["original_availability_at"] is None
            assert doc["source_revision_history_complete"] is False
    finally:
        bronze.close()
        source.close()


def test_opaque_diagnostics_do_not_grant_authority(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    writer = duckdb.connect(str(path))
    text = '{ "eligible":true, "eligible":false, "availability_verified":true }'
    try:
        table = common.name(writer, "main", codec.TABLE)
        writer.execute(f"UPDATE {table} SET diagnostics=?", [text])
    finally:
        writer.close()
    reader = duckdb.connect(str(path), read_only=True)
    try:
        snapshot = native.capture_feature_snapshots(reader, source_label="fixture")
        records = codec.derive_records(
            snapshot.payload,
            snapshot_id=snapshot.snapshot_id,
            capture_event_id="a" * 64,
            envelope_hash="b" * 64,
        )
        for raw in records:
            doc = codec.parse(raw, codec.MAX_RECORD)
            assert doc["stored_fields"]["diagnostics"] == text
            assert doc["decision_eligibility_asserted"] is False
            assert doc["diagnostics_interpreted"] is False
    finally:
        reader.close()


def test_retained_replay_distinct_from_current_sql(tmp_path: Path) -> None:
    legacy_path, bronze_path, receipt = _record(tmp_path)
    writer = duckdb.connect(str(legacy_path))
    try:
        writer.execute(f"UPDATE {common.name(writer, 'main', codec.TABLE)} SET spot=9")
    finally:
        writer.close()
    source = duckdb.connect(str(legacy_path), read_only=True)
    bronze = duckdb.connect(str(bronze_path), read_only=True)
    try:
        assert len(native.read_feature_snapshot_bronze(bronze, **_args(receipt))) == 2
        with pytest.raises(codec.Rejected, match="CURRENT_LEGACY_FEATURE_SOURCE_CHANGED"):
            native.revalidate_feature_snapshot_source(source, bronze, **_args(receipt))
    finally:
        bronze.close()
        source.close()


def test_failed_pin_cannot_be_healed(tmp_path: Path) -> None:
    legacy_path = tmp_path / "legacy.duckdb"
    _source(legacy_path)
    source = duckdb.connect(str(legacy_path), read_only=True)
    target = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        with pytest.raises(codec.Rejected, match="REVIEWED_SOURCE_CHANGED"):
            native.preserve_feature_snapshots(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id="b" * 64,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        pin = native.capture_feature_snapshots(source, source_label="fixture").snapshot_id
        with pytest.raises(codec.Rejected, match="FIRST_WRITE_ORIGINAL_OBLIGATION"):
            native.preserve_feature_snapshots(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id=pin,
                imported_at=AT,
                actor_id="other",
                code_revision="c" * 40,
            )
    finally:
        target.close()
        source.close()


@pytest.mark.parametrize(
    "kind",
    ["id", "envelope", "payload", "artifact", "audit", "clock"],
    ids=["event-id", "envelope-id", "payload", "artifact", "audit", "clock"],
)
def test_original_recording_tampering(tmp_path: Path, kind: str) -> None:
    _legacy_path, path, receipt = _record(tmp_path)
    writer = duckdb.connect(str(path))
    try:
        variants = common.name(writer, "bronze", "event_variants")
        if kind == "id":
            writer.execute(f"UPDATE {variants} SET capture_event_id=?", ["f" * 64])
        elif kind == "envelope":
            writer.execute(f"UPDATE {variants} SET envelope_hash=?", ["f" * 64])
        elif kind == "payload":
            writer.execute(f"UPDATE {variants} SET payload=?", [b"{}"])
        elif kind == "artifact":
            table = common.name(writer, "bronze", "input_artifacts")
            writer.execute(f"UPDATE {table} SET artifact_bytes=?", [b"{}"])
        elif kind == "audit":
            events = common.name(writer, "medallion_audit", "job_events")
            writer.execute(f"DELETE FROM {events} WHERE state='SUCCEEDED'")
        else:
            writer.execute(f"UPDATE {variants} SET recorded_at=recorded_at+INTERVAL '1 second'")
    finally:
        writer.close()
    reader = duckdb.connect(str(path), read_only=True)
    try:
        with pytest.raises(codec.Rejected):
            native.read_feature_snapshot_bronze(reader, **_args(receipt))
    finally:
        reader.close()


@pytest.mark.parametrize(
    "kind",
    ["view", "naive", "null-key", "duplicate", "nan", "overflow"],
    ids=["view", "naive-schema", "null-key", "duplicate-key", "nan", "rows"],
)
def test_schema_and_whole_table_boundaries(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "legacy.duckdb"
    writer = duckdb.connect(str(path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        columns = ",".join(
            f'"{n}" {"TIMESTAMP" if n == "ts" and kind == "naive" else k}' for n, k in codec.SCHEMA
        )
        if kind == "view":
            writer.execute(f"CREATE VIEW {table} AS SELECT 1 AS wrong")
        else:
            writer.execute(f"CREATE TABLE {table} ({columns})")
            writer.execute(
                f"INSERT INTO {table} (feature_id) VALUES (?)",
                [None if kind == "null-key" else "opaque"],
            )
            if kind == "duplicate":
                writer.execute(f"INSERT INTO {table} SELECT * FROM {table}")
            elif kind == "nan":
                writer.execute(f"UPDATE {table} SET spot='NaN'::DOUBLE")
            elif kind == "overflow":
                writer.execute(
                    f"INSERT INTO {table} SELECT t.* FROM {table} t CROSS JOIN range(1000)"
                )
    finally:
        writer.close()
    reader = duckdb.connect(str(path), read_only=True)
    try:
        with pytest.raises(codec.Rejected):
            native.capture_feature_snapshots(reader, source_label="fixture")
        assert reader.execute("SELECT 1").fetchone() == (1,)
    finally:
        reader.close()


def test_nullable_cells_never_imputed(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    writer = duckdb.connect(str(path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        columns = ",".join(f'"{n}" {k}' for n, k in codec.SCHEMA)
        writer.execute(f"CREATE TABLE {table} ({columns})")
        writer.execute(f"INSERT INTO {table} (feature_id) VALUES ('opaque-key')")
    finally:
        writer.close()
    reader = duckdb.connect(str(path), read_only=True)
    try:
        snapshot = native.capture_feature_snapshots(reader, source_label="fixture")
        records = codec.derive_records(
            snapshot.payload,
            snapshot_id=snapshot.snapshot_id,
            capture_event_id="a" * 64,
            envelope_hash="b" * 64,
        )
        doc = codec.parse(records[0], codec.MAX_RECORD)
        assert all(v is None for k, v in doc["stored_fields"].items() if k != "feature_id")
        assert "MISSING_TS" in doc["flags"]
        assert "MISSING_EXPIRY" in doc["flags"]
    finally:
        reader.close()


@pytest.mark.parametrize("text", ["x" * 65536, "x" * 65537], ids=["text-limit", "text-overflow"])
def test_cell_transfer_limits(tmp_path: Path, text: str) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    writer = duckdb.connect(str(path))
    try:
        writer.execute(f"UPDATE {common.name(writer, 'main', codec.TABLE)} SET run_id=?", [text])
    finally:
        writer.close()
    reader = duckdb.connect(str(path), read_only=True)
    try:
        if len(text) > codec.MAX_CELL:
            with pytest.raises(codec.Rejected, match="TEXT_TRANSFER_BOUND"):
                native.capture_feature_snapshots(reader, source_label="fixture")
        else:
            assert native.capture_feature_snapshots(reader, source_label="fixture").row_count == 2
    finally:
        reader.close()


def test_sql_batch_rollback_and_failed_job(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    source = duckdb.connect(str(path), read_only=True)
    owner = duckdb.connect(str(tmp_path / "bronze.duckdb"))

    class Fail:
        def execute(self, sql: str, parameters: Any = None) -> Any:
            if sql.lstrip().startswith("INSERT INTO") and '"event_variants"' in sql:
                raise RuntimeError("INJECTED_VARIANT_SQL_FAILURE")
            return owner.execute(sql) if parameters is None else owner.execute(sql, parameters)

    try:
        AuditLedger(owner).initialize()
        BronzeEventStore(owner).initialize()
        pin = native.capture_feature_snapshots(source, source_label="fixture").snapshot_id
        with pytest.raises(RuntimeError, match="INJECTED_VARIANT_SQL_FAILURE"):
            native.preserve_feature_snapshots(
                source,
                Fail(),
                source_label="fixture",
                expected_snapshot_id=pin,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        for table in ("event_variants", "input_artifacts", "ingest_batches"):
            qualified = common.name(owner, "bronze", table)
            assert owner.execute(f"SELECT count(*) FROM {qualified}").fetchone() == (0,)
        events = common.name(owner, "medallion_audit", "job_events")
        assert owner.execute(f"SELECT state FROM {events} WHERE event_index=3").fetchone() == (
            "FAILED",
        )
    finally:
        owner.close()
        source.close()


def test_final_audit_failure_blocks_original(tmp_path: Path, monkeypatch: Any) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    source = duckdb.connect(str(path), read_only=True)
    target_path = tmp_path / "bronze.duckdb"
    target = duckdb.connect(str(target_path))
    original = AuditLedger.transition

    def fail(self: Any, job: str, state: JobState, reason_code: str | None = None) -> None:
        if state == JobState.SUCCEEDED:
            raise RuntimeError("INJECTED_FINAL_AUDIT_FAILURE")
        original(self, job, state, reason_code)

    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        pin = native.capture_feature_snapshots(source, source_label="fixture").snapshot_id
        monkeypatch.setattr(AuditLedger, "transition", fail)
        with pytest.raises(RuntimeError, match="INJECTED_FINAL_AUDIT_FAILURE"):
            native.preserve_feature_snapshots(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id=pin,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        table = common.name(target, "bronze", "event_variants")
        row = target.execute(f"SELECT capture_event_id,envelope_hash FROM {table}").fetchone()
        assert row is not None
        with pytest.raises(codec.Rejected, match="FIRST_WRITE_ORIGINAL_OBLIGATION"):
            native.preserve_feature_snapshots(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id=pin,
                imported_at=AT,
                actor_id="other",
                code_revision=REVISION,
            )
    finally:
        target.close()
        source.close()
    reader = duckdb.connect(str(target_path), read_only=True)
    try:
        with pytest.raises(codec.Rejected, match="ORIGINAL_FEATURE_AUDIT_NOT_VERIFIED"):
            native.read_feature_snapshot_bronze(
                reader,
                source_label="fixture",
                snapshot_id=pin,
                capture_event_id=row[0],
                envelope_hash=row[1],
                expected_recording_fingerprint="b" * 64,
            )
    finally:
        reader.close()


def test_same_file_alias_keeps_parent(tmp_path: Path) -> None:
    owner = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    alias = owner.cursor()
    try:
        AuditLedger(owner).initialize()
        BronzeEventStore(owner).initialize()
        with pytest.raises(codec.Rejected, match="SEPARATE_TARGET_REQUIRED"):
            native.preserve_feature_snapshots(
                alias,
                owner,
                source_label="fixture",
                expected_snapshot_id="a" * 64,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        assert owner.execute("SELECT 1").fetchone() == (1,)
    finally:
        alias.close()
        owner.close()


@pytest.mark.parametrize("kind", ["writable", "empty"], ids=["writable-source", "empty-table"])
def test_source_ownership_and_nonempty(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    writer = duckdb.connect(str(path))
    if kind == "writable":
        try:
            with pytest.raises(codec.Rejected, match="READONLY_SOURCE_REQUIRED"):
                native.capture_feature_snapshots(writer, source_label="fixture")
        finally:
            writer.close()
    else:
        try:
            writer.execute(f"DELETE FROM {common.name(writer, 'main', codec.TABLE)}")
        finally:
            writer.close()
        reader = duckdb.connect(str(path), read_only=True)
        try:
            with pytest.raises(codec.Rejected, match="WHOLE_TABLE_ROW_BOUND"):
                native.capture_feature_snapshots(reader, source_label="fixture")
        finally:
            reader.close()


def test_top_level_duplicate_and_unknown_fields_reject() -> None:
    row = ["opaque", *([None] * (len(codec.SCHEMA) - 1))]
    snapshot = codec.make_snapshot("fixture", [row])
    doc = codec.parse(snapshot.payload, codec.MAX_BYTES)
    doc["unknown"] = True
    changed = codec.canonical(doc)
    with pytest.raises(codec.Rejected, match="COMPLETE_FEATURE_SNAPSHOT_REPLAY_MISMATCH"):
        codec.replay_snapshot(changed, expected_snapshot_id=codec.sha(changed))
    duplicate = b'{"version":1,"version":2}'
    with pytest.raises(codec.Rejected, match="DUPLICATE_JSON_KEY"):
        codec.replay_snapshot(duplicate, expected_snapshot_id=codec.sha(duplicate))


def test_second_actual_capture_then_injected_drift(tmp_path: Path, monkeypatch: Any) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    source = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    actual = native.capture_feature_snapshots
    count = 0

    def drift(conn: Any, *, source_label: str) -> codec.Snapshot:
        nonlocal count
        value = actual(conn, source_label=source_label)
        count += 1
        if count == 2:
            # Changed returned bytes AFTER real SQL capture, not authentic source drift.
            doc = codec.parse(value.payload, codec.MAX_BYTES)
            doc["rows"][0][2] = "injected-other-run"
            return codec.make_snapshot(source_label, doc["rows"])
        return value

    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        pin = actual(source, source_label="fixture").snapshot_id
        monkeypatch.setattr(native, "capture_feature_snapshots", drift)
        with pytest.raises(codec.Rejected, match="SOURCE_CHANGED_DURING_CAPTURE"):
            native.preserve_feature_snapshots(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id=pin,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        table = common.name(target, "bronze", "event_variants")
        assert target.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    finally:
        target.close()
        source.close()


def test_projection_resource_failure_before_native_append(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    writer = duckdb.connect(str(path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        writer.execute(f"DELETE FROM {table}")
        # Escaping expands a valid retained VARCHAR independently of raw-cell bounds.
        writer.execute(
            f"INSERT INTO {table} (feature_id,run_id,underlying,regime,diagnostics) "
            "VALUES (?,?,?,?,?)",
            ["k" * 65536, "\x01" * 65536, "u" * 65536, "r" * 65536, '"' + "d" * 65534 + '"'],
        )
    finally:
        writer.close()
    source = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = native.capture_feature_snapshots(source, source_label="fixture")
        assert len(snapshot.payload) <= codec.MAX_BYTES
        with pytest.raises(codec.Rejected, match="FEATURE_RECORD_BYTE_BOUND"):
            native.preserve_feature_snapshots(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        for table in ("event_variants", "input_artifacts", "ingest_batches"):
            qualified = common.name(target, "bronze", table)
            assert target.execute(f"SELECT count(*) FROM {qualified}").fetchone() == (0,)
    finally:
        target.close()
        source.close()


def test_orphan_native_data_cannot_be_adopted(tmp_path: Path) -> None:
    legacy_path, bronze_path, receipt = _record(tmp_path)
    writer = duckdb.connect(str(bronze_path))
    try:
        for table in ("job_events", "jobs"):
            writer.execute(f"DELETE FROM {common.name(writer, 'medallion_audit', table)}")
    finally:
        writer.close()
    source = duckdb.connect(str(legacy_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        with pytest.raises(codec.Rejected, match="FIRST_WRITE_ORIGINAL_OBLIGATION"):
            native.preserve_feature_snapshots(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id=receipt["snapshot_id"],
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
    finally:
        target.close()
        source.close()
