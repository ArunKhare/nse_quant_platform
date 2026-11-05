"""Actual layout-explicit policy Bronze -> persisted Silver, exact dates/JSON and faults."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import legacy_daily_rv_bronze as common
from nse_quant.data_platform import legacy_regime_policies as codec
from nse_quant.data_platform import legacy_regime_policy_bronze as bronze_api
from nse_quant.data_platform import legacy_regime_policy_silver_store as silver
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.regime_policy import RegimePolicy

AT = datetime(2026, 1, 1, tzinfo=UTC)
REVISION = "a" * 40
OPAQUE = '{ "eligible":true, "eligible":false, "authorized":true }'


def _bronze(
    tmp_path: Path, layout_id: str, maximum_status: str | None = None
) -> tuple[Path, silver.PolicyBronzePins]:
    legacy_path = tmp_path / "legacy.duckdb"
    bronze_path = tmp_path / "bronze.duckdb"
    writer = duckdb.connect(str(legacy_path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        columns = ",".join(f'"{n}" {k}' for n, k in codec.checked_layout(layout_id))
        writer.execute(f'CREATE TABLE {table} ({columns},PRIMARY KEY("policy_id"))')
    finally:
        writer.close()
    if layout_id == codec.CLOCK_BEFORE_RISK:
        legacy = DuckDBStore(path=legacy_path)
        try:
            policy = RegimePolicy(frozenset({"RANGE"}), {"RANGE": {"trades": 10}}, "READY")
            assert policy.is_usable is True
            args: dict[str, Any] = dict(
                policy_id="policy-A",
                symbol="NIFTY",
                train_start=date(2025, 1, 1),
                train_end=date(2025, 6, 30),
                test_start=date(2025, 7, 1),
                test_end=date(2025, 7, 31),
                policy=policy,
            )
            legacy.save_regime_policy(**args, risk_limits={"max_lots": 1})
            legacy.save_regime_policy(**args, risk_limits={"max_lots": 2})
        finally:
            legacy.close()
    else:
        # Named synthetic SQL, NOT a repaired positional legacy writer.
        writer = duckdb.connect(str(legacy_path))
        try:
            table = common.name(writer, "main", codec.TABLE)
            columns = ",".join('"' + n + '"' for n, _ in codec.SCHEMA)
            writer.execute(
                f"INSERT INTO {table} ({columns}) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [
                    "policy-A",
                    "NIFTY",
                    date(2025, 1, 1),
                    date(2025, 6, 30),
                    date(2025, 7, 1),
                    date(2025, 7, 31),
                    '["RANGE"]',
                    "{}",
                    "READY",
                    '{"max_lots":2}',
                    AT,
                ],
            )
        finally:
            writer.close()
    writer = duckdb.connect(str(legacy_path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        writer.execute(f"UPDATE {table} SET regime_metrics=?", [OPAQUE])
        writer.executemany(
            f"INSERT INTO {table} (policy_id,allowed_regimes) VALUES (?,?)",
            [("policy-B", None), ("policy-C", "null"), ("policy-D", "[]")],
        )
        if maximum_status is not None:
            writer.execute(
                f"UPDATE {table} SET selection_status=? WHERE policy_id=?",
                [maximum_status, "policy-A"],
            )
    finally:
        writer.close()
    source = duckdb.connect(str(legacy_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = bronze_api.capture_regime_policies(
            source, source_label="fixture", layout_id=layout_id
        )
        receipt = bronze_api.preserve_regime_policies(
            source,
            target,
            source_label="fixture",
            layout_id=layout_id,
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
        pins = silver.PolicyBronzePins(
            "fixture",
            layout_id,
            receipt["snapshot_id"],
            receipt["capture_event_id"],
            receipt["envelope_hash"],
            receipt["recording_fingerprint"],
        )
    finally:
        target.close()
        source.close()
    return bronze_path, pins


def _chain(
    tmp_path: Path, layout_id: str
) -> tuple[Path, Path, silver.PolicyBronzePins, dict[str, Any]]:
    path, pins = _bronze(tmp_path, layout_id)
    silver_path = tmp_path / "silver.duckdb"  # Preserve actual catalog/schema collision.
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(silver_path))
    try:
        silver.initialize_regime_policy_silver(target)
        context = silver.observe_regime_policy_bronze(bronze, pins=pins)
        receipt = silver.persist_regime_policy_silver(
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


@pytest.mark.parametrize(
    "layout_id",
    [codec.RISK_BEFORE_CLOCK, codec.CLOCK_BEFORE_RISK],
    ids=["risk-before-clock", "clock-before-risk"],
)
def test_actual_both_layout_native_chains(tmp_path: Path, layout_id: str) -> None:
    path, silver_path, pins, receipt = _chain(tmp_path, layout_id)
    bronze = duckdb.connect(str(path), read_only=True)
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        records = silver.read_regime_policy_silver(reader, **_args(receipt))
        assert records == bronze_api.read_regime_policy_bronze(bronze, **pins.reader_args())
        assert records == silver.revalidate_regime_policy_silver(bronze, reader, **_args(receipt))
        assert len(records) == 4
        docs = [codec.parse(r, codec.MAX_RECORD) for r in records]
        first = docs[0]["stored_fields"]
        assert first["regime_metrics"] == OPAQUE
        assert first["selection_status"] == "READY"
        assert first["risk_limits"] in ('{"max_lots":2}', '{"max_lots": 2}')
        assert first["created_at"] is not None
        assert first["train_start"] == "2025-01-01"
        assert [d["stored_fields"]["allowed_regimes"] for d in docs[1:]] == [None, "null", "[]"]
        columns = ",".join('"' + n + '"' for n, _ in codec.SCHEMA)
        table = common.name(reader, "silver", "policy_observations")
        stored = reader.execute(f"SELECT source_layout_id,{columns} FROM {table} ORDER BY ordinal")
        for ordinal, (row, raw) in enumerate(zip(stored.fetchall(), records, strict=True)):
            assert row == silver._values(raw)[2:]
            doc = codec.parse(raw, codec.MAX_RECORD)
            assert doc["source_layout_id"] == layout_id
            assert doc["source_ordinal"] == ordinal
            assert doc["policy_authorized"] is False
            assert doc["policy_json_interpreted"] is False
            assert doc["training_causality_verified"] is False
            assert doc["decision_eligibility_asserted"] is False
    finally:
        reader.close()
        bronze.close()


@pytest.mark.parametrize("field,kind", codec.SCHEMA, ids=[n for n, _ in codec.SCHEMA])
def test_all_eleven_materialized_fields_reconciled(tmp_path: Path, field: str, kind: str) -> None:
    _path, silver_path, _pins, receipt = _chain(tmp_path, codec.CLOCK_BEFORE_RISK)
    writer = duckdb.connect(str(silver_path))
    try:
        table = common.name(writer, "silver", "policy_observations")
        if kind == "DATE":
            value: object = date(2024, 1, 1)
        elif kind == "TIMESTAMP WITH TIME ZONE":
            value = AT + timedelta(days=1)
        elif kind == "JSON":
            value = '{"tampered":true}'
        else:
            value = "tampered-field"
        writer.execute(f'UPDATE {table} SET "{field}"=? WHERE policy_id=?', [value, "policy-A"])
    finally:
        writer.close()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        with pytest.raises(
            codec.Rejected, match="POLICY_SILVER_FULL_RECORD_RECOMPUTATION_MISMATCH"
        ):
            silver.read_regime_policy_silver(reader, **_args(receipt))
    finally:
        reader.close()


@pytest.mark.parametrize(
    "kind",
    [
        "layout",
        "bytes",
        "missing",
        "context",
        "record-bound",
        "aggregate",
        "nullable-mask",
        "link",
        "audit",
        "clock",
    ],
    ids=[
        "layout",
        "bytes",
        "missing",
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
    _path, silver_path, _pins, receipt = _chain(tmp_path, codec.CLOCK_BEFORE_RISK)
    writer = duckdb.connect(str(silver_path))
    try:
        table = common.name(writer, "silver", "policy_observations")
        sets = common.name(writer, "silver", "policy_sets")
        if kind == "layout":
            writer.execute(f"UPDATE {table} SET source_layout_id=?", [codec.RISK_BEFORE_CLOCK])
        elif kind == "bytes":
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
        elif kind == "nullable-mask":
            writer.execute(
                f"UPDATE {table} SET risk_limits=? WHERE policy_id='policy-B'",
                ["x" * (codec.MAX_CELL + 1)],
            )
        elif kind == "link":
            writer.execute(f"DELETE FROM {common.name(writer, 'silver', 'policy_attempts')}")
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
            silver.read_regime_policy_silver(reader, **_args(receipt))
    finally:
        reader.close()


def test_layout_review_failure_cannot_heal_same_scope(tmp_path: Path) -> None:
    path, pins = _bronze(tmp_path, codec.CLOCK_BEFORE_RISK)
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "silver.duckdb"))
    try:
        silver.initialize_regime_policy_silver(target)
        wrong = replace(pins, layout_id=codec.RISK_BEFORE_CLOCK)
        assert wrong.scope_id == pins.scope_id
        with pytest.raises(codec.Rejected, match="NATIVE_POLICY_ENVELOPE_OR_LAYOUT_MISMATCH"):
            silver.persist_regime_policy_silver(
                bronze,
                target,
                pins=wrong,
                expected_context_sha256="b" * 64,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        changed = replace(pins, envelope_hash="c" * 64, recording_fingerprint="d" * 64)
        with pytest.raises(codec.Rejected, match="POLICY_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"):
            silver.persist_regime_policy_silver(
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


def test_native_bronze_audit_and_legacy_sql_are_distinct_checks(tmp_path: Path) -> None:
    path, silver_path, pins, receipt = _chain(tmp_path, codec.CLOCK_BEFORE_RISK)
    legacy_path = tmp_path / "legacy.duckdb"
    writer = duckdb.connect(str(legacy_path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        writer.execute(f"UPDATE {table} SET selection_status='changed'")
    finally:
        writer.close()
    legacy = duckdb.connect(str(legacy_path), read_only=True)
    bronze = duckdb.connect(str(path), read_only=True)
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        assert len(silver.revalidate_regime_policy_silver(bronze, reader, **_args(receipt))) == 4
        with pytest.raises(codec.Rejected, match="CURRENT_LEGACY_POLICY_SOURCE_CHANGED"):
            bronze_api.revalidate_regime_policy_source(legacy, bronze, **pins.reader_args())
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
        assert len(silver.read_regime_policy_silver(reader, **_args(receipt))) == 4
        with pytest.raises(codec.Rejected, match="ORIGINAL_POLICY_AUDIT_NOT_VERIFIED"):
            silver.revalidate_regime_policy_silver(bronze, reader, **_args(receipt))
    finally:
        reader.close()
        bronze.close()


def test_partial_second_insert_rolls_back_and_blocks_retry(tmp_path: Path) -> None:
    path, pins = _bronze(tmp_path, codec.CLOCK_BEFORE_RISK)
    bronze = duckdb.connect(str(path), read_only=True)
    owner = duckdb.connect(str(tmp_path / "silver.duckdb"))

    class Fail:
        def __init__(self) -> None:
            self.count = 0

        def execute(self, sql: str, parameters: Any = None) -> Any:
            if sql.startswith("INSERT INTO") and '"policy_observations"' in sql:
                self.count += 1
                if self.count == 2:
                    raise RuntimeError("INJECTED_SECOND_INSERT_FAILURE")
            return owner.execute(sql) if parameters is None else owner.execute(sql, parameters)

    try:
        silver.initialize_regime_policy_silver(owner)
        context = silver.observe_regime_policy_bronze(bronze, pins=pins)
        with pytest.raises(RuntimeError, match="INJECTED_SECOND_INSERT_FAILURE"):
            silver.persist_regime_policy_silver(
                bronze,
                Fail(),
                pins=pins,
                expected_context_sha256=codec.sha(context),
                actor_id="synthetic",
                code_revision=REVISION,
            )
        for table in ("policy_sets", "policy_observations", "policy_attempts"):
            qualified = common.name(owner, "silver", table)
            assert owner.execute(f"SELECT count(*) FROM {qualified}").fetchone() == (0,)
        with pytest.raises(codec.Rejected, match="POLICY_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"):
            silver.persist_regime_policy_silver(
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
    path, pins = _bronze(tmp_path, codec.CLOCK_BEFORE_RISK)
    bronze = duckdb.connect(str(path), read_only=True)
    silver_path = tmp_path / "silver.duckdb"
    target = duckdb.connect(str(silver_path))
    actual = AuditLedger.transition

    def fail(self: Any, job: str, state: JobState, reason_code: str | None = None) -> None:
        if state == JobState.SUCCEEDED:
            raise RuntimeError("INJECTED_FINAL_AUDIT_FAILURE")
        actual(self, job, state, reason_code)

    try:
        silver.initialize_regime_policy_silver(target)
        context = silver.observe_regime_policy_bronze(bronze, pins=pins)
        monkeypatch.setattr(AuditLedger, "transition", fail)
        with pytest.raises(RuntimeError, match="INJECTED_FINAL_AUDIT_FAILURE"):
            silver.persist_regime_policy_silver(
                bronze,
                target,
                pins=pins,
                expected_context_sha256=codec.sha(context),
                actor_id="synthetic",
                code_revision=REVISION,
            )
        table = common.name(target, "silver", "policy_sets")
        row = target.execute(f"SELECT revision_id FROM {table}").fetchone()
        assert row is not None
        revision = row[0]
        with pytest.raises(codec.Rejected, match="POLICY_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"):
            silver.persist_regime_policy_silver(
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
        with pytest.raises(codec.Rejected, match="ORIGINAL_POLICY_SILVER_AUDIT_NOT_VERIFIED"):
            silver.read_regime_policy_silver(
                reader, revision_id=revision, expected_recording_fingerprint="b" * 64
            )
    finally:
        reader.close()


def test_alias_and_hex_predecode_guard(tmp_path: Path) -> None:
    target = duckdb.connect(str(tmp_path / "silver.duckdb"))
    alias = target.cursor()
    pins = silver.PolicyBronzePins(
        "fixture", codec.CLOCK_BEFORE_RISK, "a" * 64, "b" * 64, "c" * 64, "d" * 64
    )
    try:
        silver.initialize_regime_policy_silver(target)
        with pytest.raises(codec.Rejected, match="EMPTY_POLICY_SILVER_INITIALIZATION_REQUIRED"):
            silver.initialize_regime_policy_silver(target)
        with pytest.raises(codec.Rejected, match="SEPARATE_TARGET_REQUIRED"):
            silver.persist_regime_policy_silver(
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
    path, silver_path, pins, receipt = _chain(tmp_path, codec.CLOCK_BEFORE_RISK)
    writer = duckdb.connect(str(silver_path))
    try:
        if kind == "contract":
            table = common.name(writer, "medallion_audit", "dataset_contracts")
            writer.execute(f"UPDATE {table} SET fingerprint=?", ["f" * 64])
        elif kind == "definition":
            table = common.name(writer, "silver", "policy_versions")
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
                ("silver", "policy_sets"),
                ("silver", "policy_attempts"),
                ("medallion_audit", "job_events"),
                ("medallion_audit", "jobs"),
            ):
                writer.execute(f"DELETE FROM {common.name(writer, schema, table)}")
    finally:
        writer.close()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        with pytest.raises(codec.Rejected):
            silver.read_regime_policy_silver(reader, **_args(receipt))
    finally:
        reader.close()
    if kind == "orphan":
        bronze = duckdb.connect(str(path), read_only=True)
        target = duckdb.connect(str(silver_path))
        try:
            context = silver.observe_regime_policy_bronze(bronze, pins=pins)
            with pytest.raises(
                codec.Rejected, match="POLICY_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION"
            ):
                silver.persist_regime_policy_silver(
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


def test_aggregate_scalars_and_missing_source(tmp_path: Path) -> None:
    path, silver_path, _pins, receipt = _chain(tmp_path, codec.CLOCK_BEFORE_RISK)
    path.unlink()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        assert len(silver.read_regime_policy_silver(reader, **_args(receipt))) == 4
    finally:
        reader.close()
    writer = duckdb.connect(str(silver_path))
    try:
        table = common.name(writer, "silver", "policy_observations")
        names = [n for n, kind in codec.SCHEMA if kind in ("VARCHAR", "JSON")]
        assignment = ",".join('"' + n + '"=?' for n in names)
        writer.execute(f"UPDATE {table} SET {assignment}", ["x" * codec.MAX_CELL] * len(names))
    finally:
        writer.close()
    reader = duckdb.connect(str(silver_path), read_only=True)
    try:
        with pytest.raises(codec.Rejected, match="POLICY_SILVER_TRANSFER_BOUND"):
            silver.read_regime_policy_silver(reader, **_args(receipt))
    finally:
        reader.close()


def test_second_actual_observation_then_injected_drift(tmp_path: Path, monkeypatch: Any) -> None:
    path, pins = _bronze(tmp_path, codec.CLOCK_BEFORE_RISK)
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "silver.duckdb"))
    actual = silver.observe_regime_policy_bronze
    count = 0

    def drift(conn: Any, *, pins: silver.PolicyBronzePins) -> bytes:
        nonlocal count
        context = actual(conn, pins=pins)
        count += 1
        # Deliberate boundary after actual source verification, not authentic source drift.
        return context + b" " if count == 2 else context

    try:
        silver.initialize_regime_policy_silver(target)
        context = actual(bronze, pins=pins)
        monkeypatch.setattr(silver, "observe_regime_policy_bronze", drift)
        with pytest.raises(codec.Rejected, match="POLICY_BRONZE_CONTEXT_DRIFT"):
            silver.persist_regime_policy_silver(
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


@pytest.mark.parametrize("text", ["x" * 65536], ids=["maximum-policy-text"])
def test_maximum_text_actual_native_persistence(tmp_path: Path, text: str) -> None:
    path, pins = _bronze(tmp_path, codec.CLOCK_BEFORE_RISK, maximum_status=text)
    silver_path = tmp_path / "silver.duckdb"
    bronze = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(silver_path))
    try:
        silver.initialize_regime_policy_silver(target)
        context = silver.observe_regime_policy_bronze(bronze, pins=pins)
        receipt = silver.persist_regime_policy_silver(
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
        records = silver.read_regime_policy_silver(reader, **_args(receipt))
        fields = codec.parse(records[0], codec.MAX_RECORD)["stored_fields"]
        assert fields["selection_status"] == text
    finally:
        reader.close()


def test_frozen_physical_schema_and_pin_layout_reconciled(tmp_path: Path) -> None:
    path, pins = _bronze(tmp_path, codec.CLOCK_BEFORE_RISK)
    bronze = duckdb.connect(str(path), read_only=True)
    try:
        context = silver.observe_regime_policy_bronze(bronze, pins=pins)
        doc = codec.parse(context, silver.MAX_CONTEXT)
        snapshot = codec.parse(bytes.fromhex(doc["snapshot_hex"]), codec.MAX_BYTES)
        snapshot["physical_columns"] = codec.checked_layout(codec.RISK_BEFORE_CLOCK)
        altered = codec.canonical(snapshot)
        doc["snapshot_hex"] = altered.hex()
        doc["pins"]["snapshot_id"] = codec.sha(altered)
        with pytest.raises(codec.Rejected, match="COMPLETE_POLICY_REPLAY_MISMATCH"):
            silver._derive(codec.canonical(doc))
        wrong = codec.parse(context, silver.MAX_CONTEXT)
        wrong["pins"]["layout_id"] = codec.RISK_BEFORE_CLOCK
        with pytest.raises(codec.Rejected, match="POLICY_SOURCE_LABEL_OR_LAYOUT_MISMATCH"):
            silver._derive(codec.canonical(wrong))
    finally:
        bronze.close()
