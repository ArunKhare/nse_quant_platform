"""Actual legacy regime writer -> native Bronze -> persisted Silver and adversarial replay."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import legacy_daily_rv_bronze as common
from nse_quant.data_platform import legacy_market_regime_bronze as bronze_api
from nse_quant.data_platform import legacy_market_regime_silver_store as silver
from nse_quant.data_platform import legacy_market_regimes as codec
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore

AT = datetime(2026, 1, 1, tzinfo=UTC)
REVISION = "a" * 40
OPAQUE = '{ "eligible":true, "eligible":false, "authorized":true }'


def _bronze(tmp_path: Path) -> tuple[Path, silver.RegimeBronzePins]:
    legacy_path = tmp_path / "legacy.duckdb"
    bronze_path = tmp_path / "bronze.duckdb"
    legacy = DuckDBStore(path=legacy_path)
    try:
        args: dict[str, Any] = dict(
            symbol="NIFTY",
            trend_regime="unknown-trend",
            volatility_regime="opaque-vol",
            iv_regime="opaque-iv",
            regime="custom-label",
            features={"clock": AT},
        )
        local = AT.astimezone(timezone(timedelta(hours=5, minutes=30)))
        legacy.write_market_regime(ts=local, **args)
        legacy.write_market_regime(ts=AT, **(args | dict(trend_regime="retained-replacement")))
        table = common.name(legacy.conn, "main", codec.TABLE)
        # Opaque nested-key boundary in retained SQL, not authentic policy authority.
        legacy.conn.execute(f"UPDATE {table} SET features=?", [OPAQUE])
        legacy.conn.executemany(
            f"INSERT INTO {table} (symbol,ts,features) VALUES (?,?,?)",
            [("NULL", AT, None), ("JSONNULL", AT, "null"), ("EMPTY", AT, "{}")],
        )
    finally:
        legacy.close()
    source = duckdb.connect(str(legacy_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = bronze_api.capture_market_regimes(source, source_label="fixture")
        receipt = bronze_api.preserve_market_regimes(
            source,
            target,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
        pins = silver.RegimeBronzePins(
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


def _chain(tmp_path: Path) -> tuple[Path, Path, silver.RegimeBronzePins, dict[str, Any]]:
    path, pins = _bronze(tmp_path)
    silver_path = tmp_path / "silver.duckdb"  # Keep actual catalog/schema collision.
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(silver_path))
    try:
        silver.initialize_market_regime_silver(target)
        context = silver.observe_market_regime_bronze(bronze, pins=pins)
        receipt = silver.persist_market_regime_silver(
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


def test_actual_native_chain_reconciles_every_field_and_opaque_json(tmp_path: Path) -> None:
    path, silver_path, pins, receipt = _chain(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        records = silver.read_market_regime_silver(reader, **_args(receipt))
        assert records == bronze_api.read_market_regime_bronze(bronze, **pins.reader_args())
        assert records == silver.revalidate_market_regime_silver(bronze, reader, **_args(receipt))
        assert len(records) == 4  # same source key was replaced by offset-equivalent instant
        docs = [codec.parse(r, codec.MAX_RECORD) for r in records]
        fields = {d["stored_fields"]["symbol"]: d["stored_fields"] for d in docs}
        assert fields["NIFTY"]["features"] == OPAQUE
        assert fields["NIFTY"]["trend_regime"] == "retained-replacement"
        assert fields["NIFTY"]["ts"] == AT.isoformat()
        assert fields["NULL"]["features"] is None
        assert fields["JSONNULL"]["features"] == "null"
        assert fields["EMPTY"]["features"] == "{}"
        assert all(
            fields["NULL"][n] is None
            for n in ("trend_regime", "volatility_regime", "iv_regime", "regime")
        )
        columns = ",".join('"' + n + '"' for n, _ in codec.SCHEMA)
        table = common.name(reader, "silver", "regime_observations")
        stored = reader.execute(f"SELECT {columns} FROM {table} ORDER BY ordinal").fetchall()
        for ordinal, (row, raw) in enumerate(zip(stored, records, strict=True)):
            assert row == silver._values(raw)[2:]
            doc = codec.parse(raw, codec.MAX_RECORD)
            assert doc["source_ordinal"] == ordinal
            assert doc["features_interpreted"] is False
            assert doc["native_regime_recomputed"] is False
            assert doc["policy_authorized"] is False
            assert doc["decision_eligibility_asserted"] is False
            assert doc["original_availability_at"] is None
    finally:
        reader.close()
        bronze.close()


@pytest.mark.parametrize("field,kind", codec.SCHEMA, ids=[n for n, _ in codec.SCHEMA])
def test_all_seven_materialized_fields_reconciled(tmp_path: Path, field: str, kind: str) -> None:
    _path, silver_path, _pins, receipt = _chain(tmp_path)
    writer = duckdb.connect(str(silver_path))
    try:
        table = common.name(writer, "silver", "regime_observations")
        value: object = (
            AT + timedelta(days=1)
            if kind == "TIMESTAMP WITH TIME ZONE"
            else ('{"changed":true}' if kind == "JSON" else "changed-field")
        )
        writer.execute(f'UPDATE {table} SET "{field}"=? WHERE symbol=?', [value, "NIFTY"])
    finally:
        writer.close()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        with pytest.raises(
            codec.Rejected, match="REGIME_SILVER_FULL_RECORD_RECOMPUTATION_MISMATCH"
        ):
            silver.read_market_regime_silver(reader, **_args(receipt))
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
        table = common.name(writer, "silver", "regime_observations")
        sets = common.name(writer, "silver", "regime_sets")
        if kind == "bytes":
            writer.execute(f"UPDATE {table} SET record_bytes=? WHERE ordinal=0", [b"{}"])
        elif kind == "missing":
            writer.execute(f"DELETE FROM {table} WHERE ordinal=0")
        elif kind == "ordinal":
            writer.execute(f"UPDATE {table} SET ordinal=99 WHERE ordinal=0")
        elif kind == "context":
            writer.execute(f"UPDATE {sets} SET context=?", [b"x" * (silver.MAX_CONTEXT + 1)])
        elif kind in ("record-bound", "aggregate"):
            bound = codec.MAX_RECORD if kind == "record-bound" else codec.MAX_RECORDS
            writer.execute(
                f"UPDATE {table} SET record_bytes=? WHERE ordinal=0", [b"x" * (bound + 1)]
            )
        elif kind == "nullable-mask":
            writer.execute(
                f"UPDATE {table} SET features=? WHERE symbol='NULL'", ["x" * (codec.MAX_CELL + 1)]
            )
        elif kind == "link":
            writer.execute(f"DELETE FROM {common.name(writer, 'silver', 'regime_attempts')}")
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
            silver.read_market_regime_silver(reader, **_args(receipt))
    finally:
        reader.close()


def test_failed_review_cannot_heal_with_changed_pins(tmp_path: Path) -> None:
    path, pins = _bronze(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "silver.duckdb"))
    try:
        silver.initialize_market_regime_silver(target)
        with pytest.raises(codec.Rejected, match="REVIEWED_REGIME_CONTEXT_CHANGED"):
            silver.persist_market_regime_silver(
                bronze,
                target,
                pins=pins,
                expected_context_sha256="b" * 64,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        changed = replace(pins, envelope_hash="c" * 64, recording_fingerprint="d" * 64)
        assert changed.scope_id == pins.scope_id
        with pytest.raises(codec.Rejected, match="REGIME_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"):
            silver.persist_market_regime_silver(
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


def test_current_native_bronze_separate_from_retained_silver(tmp_path: Path) -> None:
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
        assert len(silver.read_market_regime_silver(reader, **_args(receipt))) == 4
        with pytest.raises(codec.Rejected, match="ORIGINAL_REGIME_AUDIT_NOT_VERIFIED"):
            silver.revalidate_market_regime_silver(bronze, reader, **_args(receipt))
    finally:
        reader.close()
        bronze.close()


def test_missing_bronze_does_not_block_retained_silver(tmp_path: Path) -> None:
    path, silver_path, _pins, receipt = _chain(tmp_path)
    path.unlink()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        assert len(silver.read_market_regime_silver(reader, **_args(receipt))) == 4
    finally:
        reader.close()


def test_legacy_sql_is_distinct_from_current_native_upstream(tmp_path: Path) -> None:
    path, silver_path, pins, receipt = _chain(tmp_path)
    legacy_path = tmp_path / "legacy.duckdb"
    writer = duckdb.connect(str(legacy_path))
    try:
        writer.execute(f"UPDATE {common.name(writer, 'main', codec.TABLE)} SET regime='changed'")
    finally:
        writer.close()
    legacy = duckdb.connect(str(legacy_path), read_only=True)
    bronze = duckdb.connect(str(path), read_only=True)
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        assert len(silver.revalidate_market_regime_silver(bronze, reader, **_args(receipt))) == 4
        with pytest.raises(codec.Rejected, match="CURRENT_LEGACY_REGIME_SOURCE_CHANGED"):
            bronze_api.revalidate_market_regime_source(legacy, bronze, **pins.reader_args())
    finally:
        reader.close()
        bronze.close()
        legacy.close()


def test_second_insert_failure_rolls_back_domain_and_blocks_adoption(tmp_path: Path) -> None:
    path, pins = _bronze(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    owner = duckdb.connect(str(tmp_path / "silver.duckdb"))

    class Fail:
        def __init__(self) -> None:
            self.count = 0

        def execute(self, sql: str, parameters: Any = None) -> Any:
            if sql.startswith("INSERT INTO") and '"regime_observations"' in sql:
                self.count += 1
                if self.count == 2:
                    raise RuntimeError("INJECTED_SECOND_INSERT_FAILURE")
            return owner.execute(sql) if parameters is None else owner.execute(sql, parameters)

    try:
        silver.initialize_market_regime_silver(owner)
        context = silver.observe_market_regime_bronze(bronze, pins=pins)
        with pytest.raises(RuntimeError, match="INJECTED_SECOND_INSERT_FAILURE"):
            silver.persist_market_regime_silver(
                bronze,
                Fail(),
                pins=pins,
                expected_context_sha256=codec.sha(context),
                actor_id="synthetic",
                code_revision=REVISION,
            )
        for table in ("regime_sets", "regime_observations", "regime_attempts"):
            qualified = common.name(owner, "silver", table)
            assert owner.execute(f"SELECT count(*) FROM {qualified}").fetchone() == (0,)
        with pytest.raises(codec.Rejected, match="REGIME_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"):
            silver.persist_market_regime_silver(
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
    silver_path = tmp_path / "silver.duckdb"
    target = duckdb.connect(str(silver_path))
    actual = AuditLedger.transition

    def fail(self: Any, job: str, state: JobState, reason_code: str | None = None) -> None:
        if state == JobState.SUCCEEDED:
            raise RuntimeError("INJECTED_FINAL_AUDIT_FAILURE")
        actual(self, job, state, reason_code)

    try:
        silver.initialize_market_regime_silver(target)
        context = silver.observe_market_regime_bronze(bronze, pins=pins)
        monkeypatch.setattr(AuditLedger, "transition", fail)
        with pytest.raises(RuntimeError, match="INJECTED_FINAL_AUDIT_FAILURE"):
            silver.persist_market_regime_silver(
                bronze,
                target,
                pins=pins,
                expected_context_sha256=codec.sha(context),
                actor_id="synthetic",
                code_revision=REVISION,
            )
        table = common.name(target, "silver", "regime_sets")
        row = target.execute(f"SELECT revision_id FROM {table}").fetchone()
        assert row is not None
        revision = row[0]
        with pytest.raises(codec.Rejected, match="REGIME_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"):
            silver.persist_market_regime_silver(
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
        with pytest.raises(codec.Rejected, match="ORIGINAL_REGIME_SILVER_AUDIT_NOT_VERIFIED"):
            silver.read_market_regime_silver(
                reader, revision_id=revision, expected_recording_fingerprint="b" * 64
            )
    finally:
        reader.close()


def test_second_actual_observation_then_injected_drift(tmp_path: Path, monkeypatch: Any) -> None:
    path, pins = _bronze(tmp_path)
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "silver.duckdb"))
    actual = silver.observe_market_regime_bronze
    count = 0

    def drift(conn: Any, *, pins: silver.RegimeBronzePins) -> bytes:
        nonlocal count
        context = actual(conn, pins=pins)
        count += 1
        # Negative boundary after actual native observation, not authentic source drift.
        return context + b" " if count == 2 else context

    try:
        silver.initialize_market_regime_silver(target)
        context = actual(bronze, pins=pins)
        monkeypatch.setattr(silver, "observe_market_regime_bronze", drift)
        with pytest.raises(codec.Rejected, match="REGIME_BRONZE_CONTEXT_DRIFT"):
            silver.persist_market_regime_silver(
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


def test_alias_initialization_and_hex_predecode(tmp_path: Path) -> None:
    target = duckdb.connect(str(tmp_path / "silver.duckdb"))
    alias = target.cursor()
    pins = silver.RegimeBronzePins("fixture", "a" * 64, "b" * 64, "c" * 64, "d" * 64)
    try:
        silver.initialize_market_regime_silver(target)
        with pytest.raises(codec.Rejected, match="EMPTY_REGIME_SILVER_INITIALIZATION_REQUIRED"):
            silver.initialize_market_regime_silver(target)
        with pytest.raises(codec.Rejected, match="SEPARATE_TARGET_REQUIRED"):
            silver.persist_market_regime_silver(
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
def test_contract_original_jobs_and_orphans(tmp_path: Path, kind: str) -> None:
    path, silver_path, pins, receipt = _chain(tmp_path)
    writer = duckdb.connect(str(silver_path))
    try:
        if kind == "contract":
            table = common.name(writer, "medallion_audit", "dataset_contracts")
            writer.execute(f"UPDATE {table} SET fingerprint=?", ["f" * 64])
        elif kind == "definition":
            table = common.name(writer, "silver", "regime_versions")
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
                ("silver", "regime_sets"),
                ("silver", "regime_attempts"),
                ("medallion_audit", "job_events"),
                ("medallion_audit", "jobs"),
            ):
                writer.execute(f"DELETE FROM {common.name(writer, schema, table)}")
    finally:
        writer.close()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        with pytest.raises(codec.Rejected):
            silver.read_market_regime_silver(reader, **_args(receipt))
    finally:
        reader.close()
    if kind == "orphan":
        bronze = duckdb.connect(str(path), read_only=True)
        target = duckdb.connect(str(silver_path))
        try:
            context = silver.observe_market_regime_bronze(bronze, pins=pins)
            with pytest.raises(
                codec.Rejected, match="REGIME_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"
            ):
                silver.persist_market_regime_silver(
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


@pytest.mark.parametrize("text", ["x" * 65536], ids=["maximum-retained-label"])
def test_maximum_label_actual_native_persistence(tmp_path: Path, text: str) -> None:
    legacy_path = tmp_path / "legacy.duckdb"
    bronze_path = tmp_path / "bronze.duckdb"
    silver_path = tmp_path / "silver.duckdb"
    legacy = DuckDBStore(path=legacy_path)
    try:
        legacy.write_market_regime(
            symbol="N",
            ts=AT,
            trend_regime=text,
            volatility_regime="custom",
            iv_regime="custom",
            regime="custom",
            features={},
        )
    finally:
        legacy.close()
    source = duckdb.connect(str(legacy_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = bronze_api.capture_market_regimes(source, source_label="maximum")
        receipt = bronze_api.preserve_market_regimes(
            source,
            target,
            source_label="maximum",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
        pins = silver.RegimeBronzePins(
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
        silver.initialize_market_regime_silver(target)
        context = silver.observe_market_regime_bronze(bronze, pins=pins)
        result = silver.persist_market_regime_silver(
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
        records = silver.read_market_regime_silver(reader, **_args(result))
        assert codec.parse(records[0], codec.MAX_RECORD)["stored_fields"]["trend_regime"] == text
    finally:
        reader.close()


def test_aggregate_scalar_preflight_is_independent_of_record_bytes(tmp_path: Path) -> None:
    _path, silver_path, _pins, receipt = _chain(tmp_path)
    writer = duckdb.connect(str(silver_path))
    try:
        table = common.name(writer, "silver", "regime_observations")
        columns = [n for n, kind in codec.SCHEMA if kind in ("VARCHAR", "JSON")]
        assignment = ",".join('"' + n + '"=?' for n in columns)
        # Every cell fits independently; four rows exceed the scalar aggregate bound.
        writer.execute(f"UPDATE {table} SET {assignment}", ["x" * codec.MAX_CELL] * len(columns))
    finally:
        writer.close()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        with pytest.raises(codec.Rejected, match="REGIME_SILVER_TRANSFER_BOUND"):
            silver.read_market_regime_silver(reader, **_args(receipt))
    finally:
        reader.close()
