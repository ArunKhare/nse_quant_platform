"""Actual policy model/writer on explicit appended layout; both native layout profiles."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import legacy_daily_rv_bronze as common
from nse_quant.data_platform import legacy_regime_policies as codec
from nse_quant.data_platform import legacy_regime_policy_bronze as native
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.regime_policy import RegimePolicy

AT = datetime(2026, 1, 1, tzinfo=UTC)
REVISION = "a" * 40
OPAQUE = '{ "eligible":true, "eligible":false, "authorized":true }'


def _table(path: Path, layout_id: str) -> None:
    writer = duckdb.connect(str(path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        columns = ",".join(f'"{n}" {k}' for n, k in codec.checked_layout(layout_id))
        writer.execute(f'CREATE TABLE {table} ({columns},PRIMARY KEY("policy_id"))')
    finally:
        writer.close()


def _source(path: Path, layout_id: str) -> None:
    _table(path, layout_id)
    policy = RegimePolicy(frozenset({"RANGE"}), {"RANGE": {"trades": 10, "pnl": 100.0}}, "READY")
    assert policy.is_usable is True  # source model usability never grants native authorization
    if layout_id == codec.CLOCK_BEFORE_RISK:
        legacy = DuckDBStore(path=path)
        try:
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
        # Fresh layout uses explicit named synthetic INSERT, NOT a repaired legacy writer.
        writer = duckdb.connect(str(path))
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
                    '{"RANGE":{"trades":10,"pnl":100.0}}',
                    "READY",
                    '{"max_lots":2}',
                    AT,
                ],
            )
        finally:
            writer.close()
    writer = duckdb.connect(str(path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        # Opaque boundary payload; not authenticated issuer or operating authority.
        writer.execute(f"UPDATE {table} SET regime_metrics=?", [OPAQUE])
        writer.executemany(
            f"INSERT INTO {table} (policy_id,allowed_regimes) VALUES (?,?)",
            [("policy-B", None), ("policy-C", "null"), ("policy-D", "[]")],
        )
    finally:
        writer.close()


def _record(tmp_path: Path, layout_id: str) -> tuple[Path, Path, dict[str, Any]]:
    source_path = tmp_path / "legacy.duckdb"
    bronze_path = tmp_path / "bronze.duckdb"
    _source(source_path, layout_id)
    source = duckdb.connect(str(source_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = native.capture_regime_policies(
            source, source_label="fixture", layout_id=layout_id
        )
        receipt = native.preserve_regime_policies(
            source,
            target,
            source_label="fixture",
            layout_id=layout_id,
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
    finally:
        target.close()
        source.close()
    return source_path, bronze_path, receipt


def _args(receipt: dict[str, Any]) -> dict[str, str]:
    return dict(
        source_label=receipt["source_label"],
        layout_id=receipt["layout_id"],
        snapshot_id=receipt["snapshot_id"],
        capture_event_id=receipt["capture_event_id"],
        envelope_hash=receipt["envelope_hash"],
        expected_recording_fingerprint=receipt["recording_fingerprint"],
    )


@pytest.mark.parametrize(
    "layout_id",
    [codec.RISK_BEFORE_CLOCK, codec.CLOCK_BEFORE_RISK],
    ids=["fresh-risk-before-clock", "appended-risk-after-clock"],
)
def test_both_actual_physical_layouts_producer_reader(tmp_path: Path, layout_id: str) -> None:
    source_path, bronze_path, receipt = _record(tmp_path, layout_id)
    source = duckdb.connect(str(source_path), read_only=True)
    bronze = duckdb.connect(str(bronze_path), read_only=True)
    try:
        records = native.read_regime_policy_bronze(bronze, **_args(receipt))
        assert records == native.revalidate_regime_policy_source(source, bronze, **_args(receipt))
        assert len(records) == 4
        table = common.name(source, "main", codec.TABLE)
        columns = ",".join('"' + n + '"' for n, _ in codec.SCHEMA)
        rows = source.execute(f"SELECT {columns} FROM {table} ORDER BY policy_id").fetchall()
        for ordinal, (row, raw) in enumerate(zip(rows, records, strict=True)):
            doc = codec.parse(raw, codec.MAX_RECORD)
            assert doc["source_layout_id"] == layout_id
            assert doc["source_ordinal"] == ordinal
            assert doc["stored_fields"] == {
                n: codec.encode_cell(v, kind)
                for v, (n, kind) in zip(row, codec.SCHEMA, strict=True)
            }
            assert doc["policy_authorized"] is False
            assert doc["policy_json_interpreted"] is False
            assert doc["training_causality_verified"] is False
            assert doc["decision_eligibility_asserted"] is False
            assert doc["original_availability_at"] is None
        fields = codec.parse(records[0], codec.MAX_RECORD)["stored_fields"]
        assert fields["selection_status"] == "READY"
        assert fields["regime_metrics"] == OPAQUE
        assert fields["risk_limits"] in ('{"max_lots":2}', '{"max_lots": 2}')
        assert fields["created_at"] is not None
        assert [
            codec.parse(r, codec.MAX_RECORD)["stored_fields"]["allowed_regimes"]
            for r in records[1:]
        ] == [None, "null", "[]"]
    finally:
        bronze.close()
        source.close()


def test_inspected_positional_writer_does_not_fit_fresh_declared_order(tmp_path: Path) -> None:
    legacy = DuckDBStore(path=tmp_path / "fresh.duckdb")
    try:
        columns = legacy.conn.execute(
            "SELECT column_name,data_type FROM information_schema.columns "
            "WHERE table_catalog=current_database() AND table_schema='main' "
            "AND table_name='regime_policies' ORDER BY ordinal_position"
        ).fetchall()
        assert tuple(columns) == codec.checked_layout(codec.RISK_BEFORE_CLOCK)
        policy = RegimePolicy(frozenset({"RANGE"}), {}, "READY")
        # Negative source-boundary test; this package neither repairs nor calls this in production.
        with pytest.raises(duckdb.Error):
            legacy.save_regime_policy(
                policy_id="P",
                symbol="NIFTY",
                train_start=date(2025, 1, 1),
                train_end=date(2025, 6, 30),
                test_start=date(2025, 7, 1),
                test_end=date(2025, 7, 31),
                policy=policy,
                risk_limits={"max_lots": 2},
            )
        table = common.name(legacy.conn, "main", codec.TABLE)
        assert legacy.conn.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    finally:
        legacy.close()


def test_layout_not_guessed_and_change_cannot_heal_failed_scope(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path, codec.CLOCK_BEFORE_RISK)
    source = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    try:
        with pytest.raises(codec.Rejected, match="EXACT_REVIEWED_POLICY_SCHEMA_REQUIRED"):
            native.capture_regime_policies(
                source, source_label="fixture", layout_id=codec.RISK_BEFORE_CLOCK
            )
        snapshot = native.capture_regime_policies(
            source, source_label="fixture", layout_id=codec.CLOCK_BEFORE_RISK
        )
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        with pytest.raises(codec.Rejected, match="EXACT_REVIEWED_POLICY_SCHEMA_REQUIRED"):
            native.preserve_regime_policies(
                source,
                target,
                source_label="fixture",
                layout_id=codec.RISK_BEFORE_CLOCK,
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        with pytest.raises(codec.Rejected, match="FIRST_WRITE_ORIGINAL_OBLIGATION"):
            native.preserve_regime_policies(
                source,
                target,
                source_label="fixture",
                layout_id=codec.CLOCK_BEFORE_RISK,
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=AT,
                actor_id="other",
                code_revision=REVISION,
            )
    finally:
        target.close()
        source.close()


@pytest.mark.parametrize(
    "kind",
    ["id", "payload", "artifact", "audit", "clock", "layout"],
    ids=["id", "payload", "artifact", "audit", "clock", "reviewed-layout"],
)
def test_original_native_recording_faults(tmp_path: Path, kind: str) -> None:
    _source_path, bronze_path, receipt = _record(tmp_path, codec.CLOCK_BEFORE_RISK)
    if kind == "layout":
        receipt["layout_id"] = codec.RISK_BEFORE_CLOCK
    else:
        writer = duckdb.connect(str(bronze_path))
        try:
            variants = common.name(writer, "bronze", "event_variants")
            if kind == "id":
                writer.execute(f"UPDATE {variants} SET capture_event_id=?", ["f" * 64])
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
    reader = duckdb.connect(str(bronze_path), read_only=True)
    try:
        with pytest.raises(codec.Rejected):
            native.read_regime_policy_bronze(reader, **_args(receipt))
    finally:
        reader.close()


def test_current_sql_change_distinct_from_retained_read(tmp_path: Path) -> None:
    source_path, bronze_path, receipt = _record(tmp_path, codec.CLOCK_BEFORE_RISK)
    writer = duckdb.connect(str(source_path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        writer.execute(f"UPDATE {table} SET selection_status='changed'")
    finally:
        writer.close()
    source = duckdb.connect(str(source_path), read_only=True)
    bronze = duckdb.connect(str(bronze_path), read_only=True)
    try:
        assert len(native.read_regime_policy_bronze(bronze, **_args(receipt))) == 4
        with pytest.raises(codec.Rejected, match="CURRENT_LEGACY_POLICY_SOURCE_CHANGED"):
            native.revalidate_regime_policy_source(source, bronze, **_args(receipt))
    finally:
        bronze.close()
        source.close()


@pytest.mark.parametrize("text", ["x" * 65536, "x" * 65537], ids=["text-limit", "text-overflow"])
def test_text_cell_limit(tmp_path: Path, text: str) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path, codec.RISK_BEFORE_CLOCK)
    writer = duckdb.connect(str(path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        writer.execute(f"UPDATE {table} SET selection_status=?", [text])
    finally:
        writer.close()
    reader = duckdb.connect(str(path), read_only=True)
    try:
        if len(text) > codec.MAX_CELL:
            with pytest.raises(codec.Rejected, match="TEXT_TRANSFER_BOUND"):
                native.capture_regime_policies(
                    reader, source_label="fixture", layout_id=codec.RISK_BEFORE_CLOCK
                )
        else:
            assert (
                native.capture_regime_policies(
                    reader, source_label="fixture", layout_id=codec.RISK_BEFORE_CLOCK
                ).row_count
                == 4
            )
    finally:
        reader.close()


def test_partial_sql_batch_rollback_and_original_obligation(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path, codec.CLOCK_BEFORE_RISK)
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
        snapshot = native.capture_regime_policies(
            source, source_label="fixture", layout_id=codec.CLOCK_BEFORE_RISK
        )
        with pytest.raises(RuntimeError, match="INJECTED_VARIANT_SQL_FAILURE"):
            native.preserve_regime_policies(
                source,
                Fail(),
                source_label="fixture",
                layout_id=codec.CLOCK_BEFORE_RISK,
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        for table in ("event_variants", "input_artifacts", "ingest_batches"):
            qualified = common.name(owner, "bronze", table)
            assert owner.execute(f"SELECT count(*) FROM {qualified}").fetchone() == (0,)
        with pytest.raises(codec.Rejected, match="FIRST_WRITE_ORIGINAL_OBLIGATION"):
            native.preserve_regime_policies(
                source,
                owner,
                source_label="fixture",
                layout_id=codec.CLOCK_BEFORE_RISK,
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
    finally:
        owner.close()
        source.close()


def test_final_audit_failure_blocks_original_read(tmp_path: Path, monkeypatch: Any) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path, codec.CLOCK_BEFORE_RISK)
    source = duckdb.connect(str(path), read_only=True)
    bronze_path = tmp_path / "bronze.duckdb"
    target = duckdb.connect(str(bronze_path))
    actual = AuditLedger.transition

    def fail(self: Any, job: str, state: JobState, reason_code: str | None = None) -> None:
        if state == JobState.SUCCEEDED:
            raise RuntimeError("INJECTED_FINAL_AUDIT_FAILURE")
        actual(self, job, state, reason_code)

    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = native.capture_regime_policies(
            source, source_label="fixture", layout_id=codec.CLOCK_BEFORE_RISK
        )
        with monkeypatch.context() as patch:
            patch.setattr(AuditLedger, "transition", fail)
            with pytest.raises(RuntimeError, match="INJECTED_FINAL_AUDIT_FAILURE"):
                native.preserve_regime_policies(
                    source,
                    target,
                    source_label="fixture",
                    layout_id=codec.CLOCK_BEFORE_RISK,
                    expected_snapshot_id=snapshot.snapshot_id,
                    imported_at=AT,
                    actor_id="synthetic",
                    code_revision=REVISION,
                )
        table = common.name(target, "bronze", "event_variants")
        row = target.execute(f"SELECT capture_event_id,envelope_hash FROM {table}").fetchone()
        assert row is not None
    finally:
        target.close()
        source.close()
    reader = duckdb.connect(str(bronze_path), read_only=True)
    try:
        with pytest.raises(codec.Rejected, match="ORIGINAL_POLICY_AUDIT_NOT_VERIFIED"):
            native.read_regime_policy_bronze(
                reader,
                source_label="fixture",
                layout_id=codec.CLOCK_BEFORE_RISK,
                snapshot_id=snapshot.snapshot_id,
                capture_event_id=row[0],
                envelope_hash=row[1],
                expected_recording_fingerprint="b" * 64,
            )
    finally:
        reader.close()


def test_layout_evidence_and_date_labels_are_not_reinterpreted() -> None:
    row = [
        "P",
        None,
        "2025-07-01",
        "2025-01-01",
        "2025-08-01",
        "2025-07-31",
        "null",
        OPAQUE,
        "READY",
        "{}",
        None,
    ]
    first = codec.make_snapshot("fixture", [row], layout_id=codec.RISK_BEFORE_CLOCK)
    other = codec.make_snapshot("fixture", [row], layout_id=codec.CLOCK_BEFORE_RISK)
    assert first.snapshot_id != other.snapshot_id
    records = codec.derive_records(
        first.payload,
        snapshot_id=first.snapshot_id,
        capture_event_id="a" * 64,
        envelope_hash="b" * 64,
    )
    doc = codec.parse(records[0], codec.MAX_RECORD)
    assert "REVERSED_STORED_TRAIN_DATES" in doc["flags"]
    assert "REVERSED_STORED_TEST_DATES" in doc["flags"]
    assert doc["stored_fields"]["created_at"] is None
    assert doc["stored_fields"]["train_start"] == "2025-07-01"
    assert doc["policy_authorized"] is False
    raw = codec.parse(first.payload, codec.MAX_BYTES)
    raw["physical_columns"] = list(codec.checked_layout(codec.CLOCK_BEFORE_RISK))
    changed = codec.canonical(raw)
    with pytest.raises(codec.Rejected, match="COMPLETE_POLICY_REPLAY_MISMATCH"):
        codec.replay_snapshot(changed, expected_snapshot_id=codec.sha(changed))


def test_alias_parent_survives_and_outer_json_is_strict(tmp_path: Path) -> None:
    owner = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    alias = owner.cursor()
    try:
        AuditLedger(owner).initialize()
        BronzeEventStore(owner).initialize()
        with pytest.raises(codec.Rejected, match="SEPARATE_TARGET_REQUIRED"):
            native.preserve_regime_policies(
                alias,
                owner,
                source_label="fixture",
                layout_id=codec.RISK_BEFORE_CLOCK,
                expected_snapshot_id="a" * 64,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        assert owner.execute("SELECT 1").fetchone() == (1,)
    finally:
        alias.close()
        owner.close()
    row = ["P", *([None] * 10)]
    with pytest.raises(codec.Rejected, match="DUPLICATE_STORED_POLICY_KEY"):
        codec.make_snapshot("fixture", [row, row], layout_id=codec.RISK_BEFORE_CLOCK)
    with pytest.raises(codec.Rejected):
        codec.make_snapshot(
            "fixture",
            [[*row[:10], datetime(2026, 1, 1).isoformat()]],
            layout_id=codec.RISK_BEFORE_CLOCK,
        )
    duplicate = b'{"version":1,"version":2}'
    with pytest.raises(codec.Rejected, match="DUPLICATE_JSON_KEY"):
        codec.replay_snapshot(duplicate, expected_snapshot_id=codec.sha(duplicate))


def test_second_actual_capture_then_injected_drift(tmp_path: Path, monkeypatch: Any) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path, codec.CLOCK_BEFORE_RISK)
    source = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    actual = native.capture_regime_policies
    count = 0

    def drift(conn: Any, *, source_label: str, layout_id: str) -> codec.Snapshot:
        nonlocal count
        value = actual(conn, source_label=source_label, layout_id=layout_id)
        count += 1
        if count == 2:
            # Boundary injection after actual SQL capture, not authentic changed-source evidence.
            doc = codec.parse(value.payload, codec.MAX_BYTES)
            doc["rows"][0][8] = "changed"
            return codec.make_snapshot(source_label, doc["rows"], layout_id=layout_id)
        return value

    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = actual(source, source_label="fixture", layout_id=codec.CLOCK_BEFORE_RISK)
        monkeypatch.setattr(native, "capture_regime_policies", drift)
        with pytest.raises(codec.Rejected, match="SOURCE_CHANGED_DURING_CAPTURE"):
            native.preserve_regime_policies(
                source,
                target,
                source_label="fixture",
                layout_id=codec.CLOCK_BEFORE_RISK,
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
    finally:
        target.close()
        source.close()


def test_row_and_projection_limits_fail_whole_capture(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    _table(path, codec.RISK_BEFORE_CLOCK)
    writer = duckdb.connect(str(path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        writer.executemany(
            f"INSERT INTO {table} (policy_id) VALUES (?)", [(f"P{i}",) for i in range(1001)]
        )
    finally:
        writer.close()
    reader = duckdb.connect(str(path), read_only=True)
    try:
        with pytest.raises(codec.Rejected, match="WHOLE_TABLE_ROW_BOUND"):
            native.capture_regime_policies(
                reader, source_label="fixture", layout_id=codec.RISK_BEFORE_CLOCK
            )
    finally:
        reader.close()
    row = [
        "p" * 65536,
        "\x01" * 65536,
        None,
        None,
        None,
        None,
        '"' + "a" * 65534 + '"',
        '"' + "m" * 65534 + '"',
        "s" * 65536,
        '"' + "r" * 65534 + '"',
        None,
    ]
    snapshot = codec.make_snapshot("fixture", [row], layout_id=codec.RISK_BEFORE_CLOCK)
    assert len(snapshot.payload) <= codec.MAX_BYTES
    with pytest.raises(codec.Rejected, match="POLICY_RECORD_BYTE_BOUND"):
        codec.derive_records(
            snapshot.payload,
            snapshot_id=snapshot.snapshot_id,
            capture_event_id="a" * 64,
            envelope_hash="b" * 64,
        )


def test_orphan_rows_cannot_be_adopted(tmp_path: Path) -> None:
    source_path, bronze_path, receipt = _record(tmp_path, codec.CLOCK_BEFORE_RISK)
    writer = duckdb.connect(str(bronze_path))
    try:
        for table in ("job_events", "jobs"):
            writer.execute(f"DELETE FROM {common.name(writer, 'medallion_audit', table)}")
    finally:
        writer.close()
    source = duckdb.connect(str(source_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        with pytest.raises(codec.Rejected, match="FIRST_WRITE_ORIGINAL_OBLIGATION"):
            native.preserve_regime_policies(
                source,
                target,
                source_label="fixture",
                layout_id=codec.CLOCK_BEFORE_RISK,
                expected_snapshot_id=receipt["snapshot_id"],
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
    finally:
        target.close()
        source.close()
