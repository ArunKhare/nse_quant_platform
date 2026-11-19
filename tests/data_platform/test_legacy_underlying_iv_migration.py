"""Actual synthetic retained SQL -> native Bronze -> persisted underlying-IV Silver."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import legacy_daily_rv_bronze as common
from nse_quant.data_platform import legacy_underlying_iv as codec
from nse_quant.data_platform import legacy_underlying_iv_bronze as bronze_api
from nse_quant.data_platform import legacy_underlying_iv_silver_store as silver
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore

AT = datetime(2026, 1, 1, tzinfo=UTC)
REVISION = "a" * 40


def _source(path: Path, underlying: str = "NIFTY") -> None:
    writer = duckdb.connect(str(path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        writer.execute(
            f"CREATE TABLE {table} (ts TIMESTAMPTZ NOT NULL,"
            "underlying VARCHAR NOT NULL,expiry DATE NOT NULL,iv DOUBLE NOT NULL,"
            "spot DOUBLE,source VARCHAR NOT NULL,PRIMARY KEY(ts,underlying,expiry))"
        )
        writer.executemany(
            f"INSERT INTO {table} VALUES (?,?,DATE '2026-01-29',?,?,?)",
            [
                (AT, underlying, -0.0, None, "atm_average_live"),
                (AT + timedelta(seconds=1), underlying, -0.25, -0.0, "arbitrary-retained-label"),
                (AT + timedelta(seconds=2), underlying, 0.25, 25000.0, "atm_average"),
            ],
        )
    finally:
        writer.close()


def _bronze(tmp_path: Path) -> tuple[Path, silver.UnderlyingIVBronzePins]:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    target_path = tmp_path / "bronze.duckdb"
    source = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(target_path))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = bronze_api.capture_underlying_iv(source, source_label="fixture")
        receipt = bronze_api.preserve_underlying_iv(
            source,
            target,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
        pins = silver.UnderlyingIVBronzePins(
            "fixture",
            receipt["snapshot_id"],
            receipt["capture_event_id"],
            receipt["envelope_hash"],
            receipt["recording_fingerprint"],
        )
    finally:
        target.close()
        source.close()
    return target_path, pins


def _chain(tmp_path: Path) -> tuple[Path, Path, silver.UnderlyingIVBronzePins, dict[str, Any]]:
    path, pins = _bronze(tmp_path)
    target_path = tmp_path / "silver.duckdb"
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(target_path))
    try:
        silver.initialize_underlying_iv_silver(target)
        context = silver.observe_underlying_iv_bronze(bronze, pins=pins)
        receipt = silver.persist_underlying_iv_silver(
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
    return path, target_path, pins, receipt


def _args(receipt: dict[str, Any]) -> dict[str, str]:
    return dict(
        revision_id=receipt["revision_id"],
        expected_recording_fingerprint=receipt["recording_fingerprint"],
    )


def test_actual_native_producer_readers_and_revalidation(tmp_path: Path) -> None:
    path, target_path, pins, receipt = _chain(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    reader = duckdb.connect(str(target_path), read_only=True)
    legacy = duckdb.connect(str(tmp_path / "legacy.duckdb"), read_only=True)
    try:
        records = silver.read_underlying_iv_silver(reader, **_args(receipt))
        assert records == bronze_api.read_underlying_iv_bronze(bronze, **pins.reader_args())
        assert records == silver.revalidate_underlying_iv_silver(bronze, reader, **_args(receipt))
        assert records == bronze_api.revalidate_underlying_iv_source(
            legacy, bronze, **pins.reader_args()
        )
        docs = [codec.parse(r, codec.MAX_RECORD) for r in records]
        assert [d["source_ordinal"] for d in docs] == [0, 1, 2]
        assert docs[0]["stored_fields"]["iv"] == (-0.0).hex()
        assert docs[0]["stored_fields"]["spot"] is None
        assert docs[1]["stored_fields"]["spot"] == (-0.0).hex()
        assert docs[1]["stored_fields"]["source"] == "arbitrary-retained-label"
        for doc in docs:
            assert doc["native_iv_recomputed"] is False
            assert doc["solver_assumptions_verified"] is False
            assert doc["canonical_identity"] is None
            assert doc["original_availability_at"] is None
            assert doc["decision_eligibility_asserted"] is False
    finally:
        legacy.close()
        reader.close()
        bronze.close()


def test_current_legacy_change_does_not_rewrite_native_layers(tmp_path: Path) -> None:
    path, target_path, pins, receipt = _chain(tmp_path)
    writer = duckdb.connect(str(tmp_path / "legacy.duckdb"))
    try:
        writer.execute(f"UPDATE {common.name(writer, 'main', codec.TABLE)} SET iv=0.9")
    finally:
        writer.close()
    legacy = duckdb.connect(str(tmp_path / "legacy.duckdb"), read_only=True)
    bronze = duckdb.connect(str(path), read_only=True)
    reader = duckdb.connect(str(target_path), read_only=True)
    try:
        assert len(silver.revalidate_underlying_iv_silver(bronze, reader, **_args(receipt))) == 3
        with pytest.raises(codec.Rejected, match="CURRENT_LEGACY_IV_SOURCE_CHANGED"):
            bronze_api.revalidate_underlying_iv_source(legacy, bronze, **pins.reader_args())
    finally:
        reader.close()
        bronze.close()
        legacy.close()


@pytest.mark.parametrize("layer", ["bronze", "silver"], ids=["bronze", "silver"])
def test_failed_review_cannot_heal(tmp_path: Path, layer: str) -> None:
    if layer == "bronze":
        path = tmp_path / "legacy.duckdb"
        _source(path)
        src = duckdb.connect(str(path), read_only=True)
        target = duckdb.connect(str(tmp_path / "bronze.duckdb"))
        try:
            AuditLedger(target).initialize()
            BronzeEventStore(target).initialize()
            with pytest.raises(codec.Rejected, match="REVIEWED_SOURCE_CHANGED"):
                bronze_api.preserve_underlying_iv(
                    src,
                    target,
                    source_label="fixture",
                    expected_snapshot_id="b" * 64,
                    imported_at=AT,
                    actor_id="synthetic",
                    code_revision=REVISION,
                )
            pin = bronze_api.capture_underlying_iv(src, source_label="fixture").snapshot_id
            with pytest.raises(codec.Rejected, match="FIRST_WRITE_ORIGINAL_OBLIGATION"):
                bronze_api.preserve_underlying_iv(
                    src,
                    target,
                    source_label="fixture",
                    expected_snapshot_id=pin,
                    imported_at=AT,
                    actor_id="other",
                    code_revision="c" * 40,
                )
        finally:
            target.close()
            src.close()
    else:
        path, pins = _bronze(tmp_path)
        src = duckdb.connect(str(path), read_only=True)
        target = duckdb.connect(str(tmp_path / "silver.duckdb"))
        try:
            silver.initialize_underlying_iv_silver(target)
            with pytest.raises(codec.Rejected, match="REVIEWED_IV_BRONZE_CONTEXT_CHANGED"):
                silver.persist_underlying_iv_silver(
                    src,
                    target,
                    pins=pins,
                    expected_context_sha256="b" * 64,
                    actor_id="synthetic",
                    code_revision=REVISION,
                )
            changed = replace(pins, envelope_hash="e" * 64, recording_fingerprint="f" * 64)
            assert changed.scope_id == pins.scope_id
            with pytest.raises(codec.Rejected, match="IV_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"):
                silver.persist_underlying_iv_silver(
                    src,
                    target,
                    pins=changed,
                    expected_context_sha256="d" * 64,
                    actor_id="other",
                    code_revision=REVISION,
                )
        finally:
            target.close()
            src.close()


@pytest.mark.parametrize(
    "kind",
    [
        "scalar",
        "spot-null",
        "source",
        "bytes",
        "coverage",
        "audit",
        "clock",
        "aggregate",
        "orphan",
        "context",
    ],
    ids=[
        "scalar",
        "spot-null",
        "source",
        "bytes",
        "coverage",
        "audit",
        "clock",
        "aggregate",
        "orphan",
        "context",
    ],
)
def test_persisted_silver_tampering(tmp_path: Path, kind: str) -> None:
    _path, target_path, _pins, receipt = _chain(tmp_path)
    writer = duckdb.connect(str(target_path))
    try:
        records = common.name(writer, "silver", "iv_observations")
        sets = common.name(writer, "silver", "iv_sets")
        if kind == "scalar":
            writer.execute(f"UPDATE {records} SET iv_hex=? WHERE ordinal=0", [(0.5).hex()])
        elif kind == "spot-null":
            writer.execute(f"UPDATE {records} SET spot_hex=? WHERE ordinal=0", [(0.0).hex()])
        elif kind == "source":
            writer.execute(f"UPDATE {records} SET stored_source='provider' WHERE ordinal=0")
        elif kind == "bytes":
            writer.execute(f"UPDATE {records} SET record_bytes=? WHERE ordinal=0", [b"{}"])
        elif kind == "coverage":
            writer.execute(f"DELETE FROM {records} WHERE ordinal=0")
        elif kind == "audit":
            events = common.name(writer, "medallion_audit", "job_events")
            writer.execute(f"DELETE FROM {events} WHERE state='SUCCEEDED'")
        elif kind == "clock":
            writer.execute(f"UPDATE {sets} SET recorded_at=recorded_at+INTERVAL '1 second'")
            writer.execute(f"UPDATE {records} SET recorded_at=recorded_at+INTERVAL '1 second'")
        elif kind == "aggregate":
            writer.execute(
                f"UPDATE {records} SET record_bytes=? WHERE ordinal=0",
                [b"x" * (codec.MAX_RECORDS + 1)],
            )
        elif kind == "context":
            writer.execute(f"UPDATE {sets} SET context=?", [b"x" * (codec.MAX_CONTEXT + 1)])
        else:
            writer.execute(f"DELETE FROM {common.name(writer, 'silver', 'iv_attempts')}")
    finally:
        writer.close()
    reader = duckdb.connect(str(target_path), read_only=True)
    try:
        with pytest.raises(codec.Rejected):
            silver.read_underlying_iv_silver(reader, **_args(receipt))
    finally:
        reader.close()


@pytest.mark.parametrize(
    "kind", ["id", "payload", "artifact", "audit"], ids=["event-id", "payload", "artifact", "audit"]
)
def test_bronze_tampering_and_retained_silver_separation(tmp_path: Path, kind: str) -> None:
    path, target_path, pins, receipt = _chain(tmp_path)
    writer = duckdb.connect(str(path))
    try:
        variants = common.name(writer, "bronze", "event_variants")
        if kind == "id":
            writer.execute(f"UPDATE {variants} SET capture_event_id=?", ["f" * 64])
        elif kind == "payload":
            writer.execute(f"UPDATE {variants} SET payload=?", [b"{}"])
        elif kind == "artifact":
            table = common.name(writer, "bronze", "input_artifacts")
            writer.execute(f"UPDATE {table} SET artifact_bytes=?", [b"{}"])
        else:
            events = common.name(writer, "medallion_audit", "job_events")
            writer.execute(f"DELETE FROM {events} WHERE state='SUCCEEDED'")
    finally:
        writer.close()
    bronze = duckdb.connect(str(path), read_only=True)
    reader = duckdb.connect(str(target_path), read_only=True)
    try:
        assert len(silver.read_underlying_iv_silver(reader, **_args(receipt))) == 3
        with pytest.raises(codec.Rejected):
            bronze_api.read_underlying_iv_bronze(bronze, **pins.reader_args())
        with pytest.raises(codec.Rejected):
            silver.revalidate_underlying_iv_silver(bronze, reader, **_args(receipt))
    finally:
        reader.close()
        bronze.close()


def test_sql_partial_failure_rolls_back_and_keeps_obligation(tmp_path: Path) -> None:
    path, pins = _bronze(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    owner = duckdb.connect(str(tmp_path / "silver.duckdb"))

    class Fail:
        def __init__(self) -> None:
            self.count = 0

        def execute(self, sql: str, parameters: Any = None) -> Any:
            if sql.startswith("INSERT INTO") and '"iv_observations"' in sql:
                self.count += 1
                if self.count == 2:
                    raise RuntimeError("INJECTED_SQL_FAILURE")
            return owner.execute(sql) if parameters is None else owner.execute(sql, parameters)

    try:
        silver.initialize_underlying_iv_silver(owner)
        context = silver.observe_underlying_iv_bronze(bronze, pins=pins)
        with pytest.raises(RuntimeError, match="INJECTED_SQL_FAILURE"):
            silver.persist_underlying_iv_silver(
                bronze,
                Fail(),
                pins=pins,
                expected_context_sha256=codec.sha(context),
                actor_id="synthetic",
                code_revision=REVISION,
            )
        for table in ("iv_sets", "iv_observations", "iv_attempts"):
            qualified = common.name(owner, "silver", table)
            assert owner.execute(f"SELECT count(*) FROM {qualified}").fetchone() == (0,)
        with pytest.raises(codec.Rejected, match="IV_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"):
            silver.persist_underlying_iv_silver(
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


def test_final_audit_failure_blocks_read_and_retry(tmp_path: Path, monkeypatch: Any) -> None:
    path, pins = _bronze(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    target_path = tmp_path / "silver.duckdb"
    target = duckdb.connect(str(target_path))
    original = AuditLedger.transition

    def fail(self: Any, job: str, state: JobState, reason_code: str | None = None) -> None:
        if state == JobState.SUCCEEDED:
            raise RuntimeError("INJECTED_FINAL_AUDIT_FAILURE")
        original(self, job, state, reason_code)

    try:
        silver.initialize_underlying_iv_silver(target)
        context = silver.observe_underlying_iv_bronze(bronze, pins=pins)
        monkeypatch.setattr(AuditLedger, "transition", fail)
        with pytest.raises(RuntimeError, match="INJECTED_FINAL_AUDIT_FAILURE"):
            silver.persist_underlying_iv_silver(
                bronze,
                target,
                pins=pins,
                expected_context_sha256=codec.sha(context),
                actor_id="synthetic",
                code_revision=REVISION,
            )
        table = common.name(target, "silver", "iv_sets")
        row = target.execute(f"SELECT revision_id FROM {table}").fetchone()
        assert row is not None
        revision = row[0]
        with pytest.raises(codec.Rejected, match="IV_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"):
            silver.persist_underlying_iv_silver(
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
        with pytest.raises(codec.Rejected, match="ORIGINAL_IV_SILVER_AUDIT_NOT_VERIFIED"):
            silver.read_underlying_iv_silver(
                reader, revision_id=revision, expected_recording_fingerprint="b" * 64
            )
    finally:
        reader.close()


def test_timezone_normalization_and_naive_encoded_rejection() -> None:
    local = AT.astimezone(timezone(timedelta(hours=5, minutes=30)))
    assert common._clock(local) == common._clock(AT)
    row = [AT.isoformat(), "N", "2026-01-29", (0.25).hex(), None, "label"]
    with pytest.raises(codec.Rejected):
        codec.make_snapshot("fixture", [[datetime(2026, 1, 1).isoformat(), *row[1:]]])
    with pytest.raises(codec.Rejected, match="DUPLICATE_STORED_KEY"):
        codec.make_snapshot("fixture", [row, row])


@pytest.mark.parametrize(
    "underlying", ["x" * 65536, "x" * 65537], ids=["text-limit", "text-overflow"]
)
def test_text_bound_from_actual_sql(tmp_path: Path, underlying: str) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path, underlying=underlying)
    reader = duckdb.connect(str(path), read_only=True)
    try:
        if len(underlying) > codec.MAX_CELL:
            with pytest.raises(codec.Rejected, match="TEXT_TRANSFER_BOUND"):
                bronze_api.capture_underlying_iv(reader, source_label="fixture")
        else:
            assert bronze_api.capture_underlying_iv(reader, source_label="fixture").row_count == 3
    finally:
        reader.close()


@pytest.mark.parametrize(
    "kind",
    ["view", "naive-schema", "null-iv", "nan", "overflow"],
    ids=["view", "naive-schema", "null-iv", "nan", "row-overflow"],
)
def test_source_rejection_boundaries(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "legacy.duckdb"
    writer = duckdb.connect(str(path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        ts_kind = "TIMESTAMP" if kind == "naive-schema" else "TIMESTAMPTZ"
        if kind == "view":
            writer.execute(
                f"CREATE VIEW {table} AS SELECT now() AS ts,'N'::VARCHAR AS underlying,"
                "DATE '2026-01-29' AS expiry,0.2::DOUBLE AS iv,"
                "NULL::DOUBLE AS spot,'label'::VARCHAR AS source"
            )
        else:
            writer.execute(
                f"CREATE TABLE {table} (ts {ts_kind},underlying VARCHAR,"
                "expiry DATE,iv DOUBLE,spot DOUBLE,source VARCHAR)"
            )
            iv = None if kind == "null-iv" else float("nan") if kind == "nan" else 0.2
            writer.execute(
                f"INSERT INTO {table} VALUES (?, 'N', DATE '2026-01-29',?,NULL,'label')", [AT, iv]
            )
            if kind == "overflow":
                writer.execute(
                    f"INSERT INTO {table} SELECT t.* FROM {table} AS t CROSS JOIN range(1000)"
                )
    finally:
        writer.close()
    reader = duckdb.connect(str(path), read_only=True)
    try:
        with pytest.raises(codec.Rejected):
            bronze_api.capture_underlying_iv(reader, source_label="fixture")
        assert reader.execute("SELECT 1").fetchone() == (1,)
    finally:
        reader.close()


def test_original_bronze_final_audit_failure_blocks_read(tmp_path: Path, monkeypatch: Any) -> None:
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
        pin = bronze_api.capture_underlying_iv(source, source_label="fixture").snapshot_id
        monkeypatch.setattr(AuditLedger, "transition", fail)
        with pytest.raises(RuntimeError, match="INJECTED_FINAL_AUDIT_FAILURE"):
            bronze_api.preserve_underlying_iv(
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
            bronze_api.preserve_underlying_iv(
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
        with pytest.raises(codec.Rejected, match="ORIGINAL_IV_AUDIT_NOT_VERIFIED"):
            bronze_api.read_underlying_iv_bronze(
                reader,
                source_label="fixture",
                snapshot_id=pin,
                capture_event_id=row[0],
                envelope_hash=row[1],
                expected_recording_fingerprint="b" * 64,
            )
    finally:
        reader.close()


def test_same_file_cursor_alias_parent_survives(tmp_path: Path) -> None:
    target = duckdb.connect(str(tmp_path / "silver.duckdb"))
    alias = target.cursor()
    pins = silver.UnderlyingIVBronzePins("fixture", "a" * 64, "b" * 64, "c" * 64, "d" * 64)
    try:
        silver.initialize_underlying_iv_silver(target)
        with pytest.raises(codec.Rejected, match="SEPARATE_TARGET_REQUIRED"):
            silver.persist_underlying_iv_silver(
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


def test_context_predecode_hex_bound() -> None:
    pins = silver.UnderlyingIVBronzePins("fixture", "a" * 64, "b" * 64, "c" * 64, "d" * 64)
    context = codec.canonical(
        dict(
            version=silver.VERSION, pins=asdict(pins), snapshot_hex="z" * (2 * codec.MAX_BYTES + 1)
        )
    )
    with pytest.raises(codec.Rejected, match="SNAPSHOT_HEX_BOUND"):
        silver._derive(context)


def test_second_actual_bronze_observation_then_injected_drift(
    tmp_path: Path, monkeypatch: Any
) -> None:
    path, pins = _bronze(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "silver.duckdb"))
    actual = silver.observe_underlying_iv_bronze
    count = 0

    def drift(conn: Any, *, pins: silver.UnderlyingIVBronzePins) -> bytes:
        nonlocal count
        value = actual(conn, pins=pins)
        count += 1
        # Boundary injection after an actual policy-free source read, not authentic source drift.
        return value + b" " if count == 2 else value

    try:
        silver.initialize_underlying_iv_silver(target)
        reviewed = actual(bronze, pins=pins)
        monkeypatch.setattr(silver, "observe_underlying_iv_bronze", drift)
        with pytest.raises(codec.Rejected, match="IV_BRONZE_CONTEXT_DRIFT"):
            silver.persist_underlying_iv_silver(
                bronze,
                target,
                pins=pins,
                expected_context_sha256=codec.sha(reviewed),
                actor_id="synthetic",
                code_revision=REVISION,
            )
        table = common.name(target, "silver", "iv_observations")
        assert target.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    finally:
        target.close()
        bronze.close()
