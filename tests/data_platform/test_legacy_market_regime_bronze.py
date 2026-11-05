"""Actual legacy regime writer -> native Bronze/audit -> source-linked projections."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import legacy_daily_rv_bronze as common
from nse_quant.data_platform import legacy_market_regime_bronze as native
from nse_quant.data_platform import legacy_market_regimes as codec
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore

AT = datetime(2026, 1, 1, tzinfo=UTC)
REVISION = "a" * 40
OPAQUE = '{ "eligible":true, "eligible":false, "authorized":true, "unknown":[1,null] }'


def _source(path: Path) -> None:
    legacy = DuckDBStore(path=path)
    try:
        local = AT.astimezone(timezone(timedelta(hours=5, minutes=30)))
        args: dict[str, Any] = dict(
            symbol="NIFTY",
            trend_regime="unreviewed-trend",
            volatility_regime="HIGH",
            iv_regime="opaque-iv",
            regime="arbitrary-regime",
            features={"clock": AT},
        )
        legacy.write_market_regime(ts=local, **args)
        legacy.write_market_regime(ts=AT, **(args | dict(trend_regime="replacement-label")))
        legacy.write_market_regime(ts=AT + timedelta(seconds=1), **args)
        table = common.name(legacy.conn, "main", codec.TABLE)
        # Opaque nested-key boundary through real retained SQL, not authenticated policy evidence.
        legacy.conn.execute(f"UPDATE {table} SET features=? WHERE ts=?", [OPAQUE, AT])
        legacy.conn.execute(
            f"INSERT INTO {table} (symbol,ts) VALUES (?,?)", ["NULL", AT + timedelta(seconds=2)]
        )
    finally:
        legacy.close()


def _record(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    source_path = tmp_path / "legacy.duckdb"
    bronze_path = tmp_path / "bronze.duckdb"
    _source(source_path)
    source = duckdb.connect(str(source_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = native.capture_market_regimes(source, source_label="fixture")
        receipt = native.preserve_market_regimes(
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
    return source_path, bronze_path, receipt


def _args(receipt: dict[str, Any]) -> dict[str, str]:
    return dict(
        source_label=receipt["source_label"],
        snapshot_id=receipt["snapshot_id"],
        capture_event_id=receipt["capture_event_id"],
        envelope_hash=receipt["envelope_hash"],
        expected_recording_fingerprint=receipt["recording_fingerprint"],
    )


def test_actual_writer_native_producer_reader_and_every_field(tmp_path: Path) -> None:
    source_path, bronze_path, receipt = _record(tmp_path)
    source = duckdb.connect(str(source_path), read_only=True)
    bronze = duckdb.connect(str(bronze_path), read_only=True)
    try:
        records = native.read_market_regime_bronze(bronze, **_args(receipt))
        assert records == native.revalidate_market_regime_source(source, bronze, **_args(receipt))
        assert len(records) == 3  # offset-equivalent original key was replaced, not added
        table = common.name(source, "main", codec.TABLE)
        names = ",".join('"' + n + '"' for n, _ in codec.SCHEMA)
        rows = source.execute(f"SELECT {names} FROM {table} ORDER BY symbol,ts").fetchall()
        for ordinal, (row, raw) in enumerate(zip(rows, records, strict=True)):
            doc = codec.parse(raw, codec.MAX_RECORD)
            expected = {
                n: codec.encode_cell(v, kind)
                for v, (n, kind) in zip(row, codec.SCHEMA, strict=True)
            }
            assert doc["stored_fields"] == expected
            assert doc["source_ordinal"] == ordinal
            assert doc["features_interpreted"] is False
            assert doc["native_regime_recomputed"] is False
            assert doc["policy_authorized"] is False
            assert doc["decision_eligibility_asserted"] is False
            assert doc["original_availability_at"] is None
        first = codec.parse(records[0], codec.MAX_RECORD)["stored_fields"]
        assert first["trend_regime"] == "replacement-label"
        assert first["features"] == OPAQUE
        assert first["ts"] == AT.isoformat()
        last = codec.parse(records[-1], codec.MAX_RECORD)["stored_fields"]
        assert all(
            last[n] is None
            for n in ("trend_regime", "volatility_regime", "iv_regime", "regime", "features")
        )
    finally:
        bronze.close()
        source.close()


def test_current_source_differs_without_invalidating_retained_replay(tmp_path: Path) -> None:
    source_path, bronze_path, receipt = _record(tmp_path)
    writer = duckdb.connect(str(source_path))
    try:
        writer.execute(f"UPDATE {common.name(writer, 'main', codec.TABLE)} SET regime='changed'")
    finally:
        writer.close()
    source = duckdb.connect(str(source_path), read_only=True)
    bronze = duckdb.connect(str(bronze_path), read_only=True)
    try:
        assert len(native.read_market_regime_bronze(bronze, **_args(receipt))) == 3
        with pytest.raises(codec.Rejected, match="CURRENT_LEGACY_REGIME_SOURCE_CHANGED"):
            native.revalidate_market_regime_source(source, bronze, **_args(receipt))
    finally:
        bronze.close()
        source.close()


def test_failed_review_cannot_heal(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    source = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        with pytest.raises(codec.Rejected, match="REVIEWED_SOURCE_CHANGED"):
            native.preserve_market_regimes(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id="b" * 64,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        pin = native.capture_market_regimes(source, source_label="fixture").snapshot_id
        with pytest.raises(codec.Rejected, match="FIRST_WRITE_ORIGINAL_OBLIGATION"):
            native.preserve_market_regimes(
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
    ids=["id", "envelope", "payload", "artifact", "audit", "clock"],
)
def test_original_recording_faults(tmp_path: Path, kind: str) -> None:
    _source_path, bronze_path, receipt = _record(tmp_path)
    writer = duckdb.connect(str(bronze_path))
    try:
        variants = common.name(writer, "bronze", "event_variants")
        if kind in ("id", "envelope"):
            column = "capture_event_id" if kind == "id" else "envelope_hash"
            writer.execute(f'UPDATE {variants} SET "{column}"=?', ["f" * 64])
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
            native.read_market_regime_bronze(reader, **_args(receipt))
    finally:
        reader.close()


@pytest.mark.parametrize(
    "kind",
    ["view", "naive", "null-key", "duplicate", "empty", "overflow"],
    ids=["view", "naive-schema", "null-key", "duplicate", "empty", "rows"],
)
def test_schema_and_key_boundaries(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "legacy.duckdb"
    writer = duckdb.connect(str(path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        if kind == "view":
            writer.execute(f"CREATE VIEW {table} AS SELECT 1 AS wrong")
        else:
            columns = ",".join(
                f'"{n}" {"TIMESTAMP" if n == "ts" and kind == "naive" else k}'
                for n, k in codec.SCHEMA
            )
            writer.execute(f"CREATE TABLE {table} ({columns})")
            if kind != "empty":
                writer.execute(
                    f"INSERT INTO {table} (symbol,ts) VALUES (?,?)",
                    [None if kind == "null-key" else "N", AT],
                )
            if kind == "duplicate":
                writer.execute(f"INSERT INTO {table} SELECT * FROM {table}")
            elif kind == "overflow":
                writer.execute(
                    f"INSERT INTO {table} SELECT t.* FROM {table} t CROSS JOIN range(1000)"
                )
    finally:
        writer.close()
    reader = duckdb.connect(str(path), read_only=True)
    try:
        with pytest.raises(codec.Rejected):
            native.capture_market_regimes(reader, source_label="fixture")
        assert reader.execute("SELECT 1").fetchone() == (1,)
    finally:
        reader.close()


@pytest.mark.parametrize("text", ["x" * 65536, "x" * 65537], ids=["text-limit", "text-overflow"])
def test_individual_text_bound(tmp_path: Path, text: str) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    writer = duckdb.connect(str(path))
    try:
        writer.execute(f"UPDATE {common.name(writer, 'main', codec.TABLE)} SET regime=?", [text])
    finally:
        writer.close()
    reader = duckdb.connect(str(path), read_only=True)
    try:
        if len(text) > codec.MAX_CELL:
            with pytest.raises(codec.Rejected, match="TEXT_TRANSFER_BOUND"):
                native.capture_market_regimes(reader, source_label="fixture")
        else:
            assert native.capture_market_regimes(reader, source_label="fixture").row_count == 3
    finally:
        reader.close()


def test_partial_batch_sql_rollback(tmp_path: Path) -> None:
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
        pin = native.capture_market_regimes(source, source_label="fixture").snapshot_id
        with pytest.raises(RuntimeError, match="INJECTED_VARIANT_SQL_FAILURE"):
            native.preserve_market_regimes(
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
    finally:
        owner.close()
        source.close()


def test_final_audit_failure_blocks_read_and_adoption(tmp_path: Path, monkeypatch: Any) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
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
        pin = native.capture_market_regimes(source, source_label="fixture").snapshot_id
        monkeypatch.setattr(AuditLedger, "transition", fail)
        with pytest.raises(RuntimeError, match="INJECTED_FINAL_AUDIT_FAILURE"):
            native.preserve_market_regimes(
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
            native.preserve_market_regimes(
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
    reader = duckdb.connect(str(bronze_path), read_only=True)
    try:
        with pytest.raises(codec.Rejected, match="ORIGINAL_REGIME_AUDIT_NOT_VERIFIED"):
            native.read_market_regime_bronze(
                reader,
                source_label="fixture",
                snapshot_id=pin,
                capture_event_id=row[0],
                envelope_hash=row[1],
                expected_recording_fingerprint="b" * 64,
            )
    finally:
        reader.close()


def test_alias_and_naive_clock(tmp_path: Path) -> None:
    owner = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    alias = owner.cursor()
    try:
        AuditLedger(owner).initialize()
        BronzeEventStore(owner).initialize()
        with pytest.raises(codec.Rejected, match="SEPARATE_TARGET_REQUIRED"):
            native.preserve_market_regimes(
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
    with pytest.raises(codec.Rejected):
        codec.make_snapshot("fixture", [["N", datetime(2026, 1, 1).isoformat(), *([None] * 5)]])


def test_second_actual_capture_then_injected_drift(tmp_path: Path, monkeypatch: Any) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    source = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    actual = native.capture_market_regimes
    count = 0

    def drift(conn: Any, *, source_label: str) -> codec.Snapshot:
        nonlocal count
        value = actual(conn, source_label=source_label)
        count += 1
        if count == 2:
            # Deliberate boundary substitution after real SQL capture, not authentic source drift.
            doc = codec.parse(value.payload, codec.MAX_BYTES)
            doc["rows"][0][5] = "injected"
            return codec.make_snapshot(source_label, doc["rows"])
        return value

    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        pin = actual(source, source_label="fixture").snapshot_id
        monkeypatch.setattr(native, "capture_market_regimes", drift)
        with pytest.raises(codec.Rejected, match="SOURCE_CHANGED_DURING_CAPTURE"):
            native.preserve_market_regimes(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id=pin,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
    finally:
        target.close()
        source.close()


def test_projection_overflow_fails_before_native_append(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    writer = duckdb.connect(str(path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        writer.execute(f"DELETE FROM {table}")
        writer.execute(
            f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?)",
            [
                "N",
                AT,
                "\x01" * 65536,
                "v" * 65536,
                "i" * 65536,
                "r" * 65536,
                '"' + "f" * 65534 + '"',
            ],
        )
    finally:
        writer.close()
    source = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = native.capture_market_regimes(source, source_label="fixture")
        assert len(snapshot.payload) <= codec.MAX_BYTES
        with pytest.raises(codec.Rejected, match="REGIME_RECORD_BYTE_BOUND"):
            native.preserve_market_regimes(
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


def test_orphan_native_rows_cannot_be_adopted(tmp_path: Path) -> None:
    source_path, bronze_path, receipt = _record(tmp_path)
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
            native.preserve_market_regimes(
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


def test_outer_contract_strict_nested_payload_opaque() -> None:
    row = ["N", AT.isoformat(), "unknown", None, None, "custom", OPAQUE]
    snapshot = codec.make_snapshot("fixture", [row])
    doc = codec.parse(snapshot.payload, codec.MAX_BYTES)
    doc["unknown"] = True
    raw = codec.canonical(doc)
    with pytest.raises(codec.Rejected, match="COMPLETE_REGIME_REPLAY_MISMATCH"):
        codec.replay_snapshot(raw, expected_snapshot_id=codec.sha(raw))
    with pytest.raises(codec.Rejected, match="DUPLICATE_STORED_REGIME_KEY"):
        codec.make_snapshot("fixture", [row, row])
    duplicate = b'{"version":1,"version":2}'
    with pytest.raises(codec.Rejected, match="DUPLICATE_JSON_KEY"):
        codec.replay_snapshot(duplicate, expected_snapshot_id=codec.sha(duplicate))


def test_sql_null_json_null_and_empty_object_remain_distinct(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    writer = duckdb.connect(str(path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        columns = ",".join(f'"{n}" {k}' for n, k in codec.SCHEMA)
        writer.execute(f"CREATE TABLE {table} ({columns})")
        writer.executemany(
            f"INSERT INTO {table} (symbol,ts,features) VALUES (?,?,?)",
            [("A", AT, None), ("B", AT, "null"), ("C", AT, "{}")],
        )
    finally:
        writer.close()
    reader = duckdb.connect(str(path), read_only=True)
    try:
        snapshot = native.capture_market_regimes(reader, source_label="fixture")
        records = codec.derive_records(
            snapshot.payload,
            snapshot_id=snapshot.snapshot_id,
            capture_event_id="a" * 64,
            envelope_hash="b" * 64,
        )
        assert [codec.parse(r, codec.MAX_RECORD)["stored_fields"]["features"] for r in records] == [
            None,
            "null",
            "{}",
        ]
    finally:
        reader.close()


def test_writable_source_rejects(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    writer = duckdb.connect(str(path))
    try:
        with pytest.raises(codec.Rejected, match="READONLY_SOURCE_REQUIRED"):
            native.capture_market_regimes(writer, source_label="fixture")
    finally:
        writer.close()
