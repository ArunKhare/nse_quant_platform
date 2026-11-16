"""Actual regime-policies writer -> plural Bronze -> persisted Silver chain."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import legacy_regime_policies as codec
from nse_quant.data_platform import legacy_regime_policies_bronze as bronze_api
from nse_quant.data_platform import legacy_regime_policies_silver_store as silver
from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore

AT = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
REVISION = "a" * 40


def _value(kind: str, index: int) -> object:
    if kind == "VARCHAR":
        return f"value-{index}"
    if kind == "JSON":
        return json.dumps({"index": index})
    if kind == "DATE":
        return AT.date()
    if kind == "TIMESTAMP WITH TIME ZONE":
        return AT
    if kind in ("BIGINT", "INTEGER"):
        return index
    if kind == "DOUBLE":
        return float(index)
    if kind == "BOOLEAN":
        return index % 2 == 0
    raise AssertionError(f"unsupported kind {kind}")


def _seed(path: Path) -> None:
    writer = duckdb.connect(str(path))
    try:
        columns = ",".join(f'"{n}" {k}' for n, k in codec.SCHEMA)
        writer.execute(f'CREATE TABLE main.{codec.TABLE} ({columns},PRIMARY KEY("policy_id"))')
        rows = []
        for index in range(3):
            rows.append(tuple(_value(kind, index) for _name, kind in codec.SCHEMA))
        writer.executemany(
            f"INSERT INTO main.{codec.TABLE} VALUES ({','.join('?' for _ in codec.SCHEMA)})",
            rows,
        )
    finally:
        writer.close()


def _bronze(tmp_path: Path) -> tuple[Path, base.SilverPins]:
    source_path, bronze_path = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    _seed(source_path)
    source = duckdb.connect(str(source_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = bronze_api.capture_regime_policies(source, source_label="fixture")
        receipt = bronze_api.preserve_regime_policies(
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
    return bronze_path, base.SilverPins(
        source_label=receipt["source_label"],
        snapshot_id=receipt["snapshot_id"],
        capture_event_id=receipt["capture_event_id"],
        envelope_hash=receipt["envelope_hash"],
        recording_fingerprint=receipt["recording_fingerprint"],
    )


def _chain(tmp_path: Path) -> tuple[Path, Path, base.SilverPins, dict[str, Any]]:
    bronze_path, pins = _bronze(tmp_path)
    silver_path = tmp_path / "regime_policies_silver.duckdb"
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        silver.initialize_regime_policies_silver(target)
        context = silver.observe_regime_policies_bronze(bronze_conn, pins=pins)
        receipt = silver.persist_regime_policies_silver(
            bronze_conn,
            target,
            pins=pins,
            expected_context_sha256=base.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver_path, pins, receipt


def test_regime_policies_bronze_to_silver_chain(tmp_path: Path) -> None:
    bronze_path, silver_path, pins, receipt = _chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path), read_only=True) as reader,
    ):
        records = silver.read_regime_policies_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )
        assert len(records) == receipt["row_count"] == 3
        assert records == bronze_api.read_regime_policies_bronze(bronze_conn, **pins.reader_args())
        revalidate_args = pins.reader_args()
        revalidate_args["revision_id"] = receipt["revision_id"]
        revalidate_args["expected_recording_fingerprint"] = receipt["recording_fingerprint"]
        revalidate_args["recording_fingerprint"] = pins.recording_fingerprint
        assert records == silver.revalidate_regime_policies_silver(
            bronze_conn,
            reader,
            **revalidate_args,
        )
        assert records == silver.revalidate_regime_policies_silver(
            bronze_conn,
            reader,
            **revalidate_args,
        )


def test_regime_policies_silver_tampering(tmp_path: Path) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("UPDATE silver.regime_policy_sets SET context='bad'::BLOB")
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError),
    ):
        silver.read_regime_policies_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_regime_policies_silver_first_write_obligation(tmp_path: Path) -> None:
    bronze_path, silver_path, pins, receipt = _chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        context = silver.observe_regime_policies_bronze(bronze_conn, pins=pins)
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            silver.persist_regime_policies_silver(
                bronze_conn,
                target,
                pins=pins,
                expected_context_sha256=base.sha(context),
                actor_id="other",
                code_revision="b" * 40,
            )


def test_regime_policies_silver_same_file_alias(tmp_path: Path) -> None:
    _bronze_path, silver_path, pins, _receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as target:
        alias = target.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                silver.persist_regime_policies_silver(
                    alias,
                    target,
                    pins=pins,
                    expected_context_sha256="a" * 64,
                    actor_id="synthetic",
                    code_revision=REVISION,
                )
            assert target.execute("SELECT 1").fetchone() == (1,)
        finally:
            alias.close()
