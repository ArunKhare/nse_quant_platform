"""Actual market-events writer -> Bronze -> persisted Silver chain."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import legacy_market_events as codec
from nse_quant.data_platform import legacy_market_events_bronze as bronze_api
from nse_quant.data_platform import legacy_market_events_silver_store as silver
from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore

AT = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
REVISION = "a" * 40
TABLE = '"main"."market_events"'


def _seed(path: Path) -> None:
    writer = duckdb.connect(str(path))
    try:
        columns = ",".join(f'"{n}" {k}' for n, k in codec.SCHEMA)
        writer.execute(f'CREATE TABLE {TABLE} ({columns},PRIMARY KEY("event_id"))')
        writer.executemany(
            f"INSERT INTO {TABLE} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    "ev-1",
                    "rss",
                    "EARNINGS",
                    "Title",
                    "Desc",
                    "NIFTY",
                    AT,
                    "HIGH",
                    100.0,
                    105.0,
                    "BEAT",
                    '["NIFTY"]',
                    "{}",
                    AT,
                ),
                ("ev-2", "rss", "GDP", None, None, None, None, None, None, None, None, None, None, None),
                (
                    "ev-3",
                    "api",
                    "CPI",
                    "Title",
                    "Desc",
                    "BANKNIFTY",
                    AT.replace(minute=16),
                    "MEDIUM",
                    None,
                    None,
                    None,
                    "[]",
                    "null",
                    AT.replace(minute=16),
                ),
                (
                    "ev-4",
                    "api",
                    "RATE",
                    "Title",
                    "Desc",
                    "NIFTY",
                    AT.replace(minute=17),
                    "LOW",
                    1.0,
                    1.0,
                    "INLINE",
                    "null",
                    "[]",
                    AT.replace(minute=17),
                ),
            ],
        )
    finally:
        writer.close()


def _bronze(tmp_path: Path) -> tuple[Path, silver.MarketEventsBronzePins]:
    source_path, bronze_path = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    _seed(source_path)
    source = duckdb.connect(str(source_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = bronze_api.capture_market_events(source, source_label="fixture")
        receipt = bronze_api.preserve_market_events(
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
    return bronze_path, silver.MarketEventsBronzePins(
        source_label=receipt["source_label"],
        snapshot_id=receipt["snapshot_id"],
        capture_event_id=receipt["capture_event_id"],
        envelope_hash=receipt["envelope_hash"],
        recording_fingerprint=receipt["recording_fingerprint"],
    )


def _chain(tmp_path: Path) -> tuple[Path, Path, silver.MarketEventsBronzePins, dict[str, Any]]:
    bronze_path, pins = _bronze(tmp_path)
    silver_path = tmp_path / "market_events_silver.duckdb"
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        silver.initialize_market_events_silver(target)
        context = silver.observe_market_events_bronze(bronze_conn, pins=pins)
        receipt = silver.persist_market_events_silver(
            bronze_conn,
            target,
            pins=pins,
            expected_context_sha256=base.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver_path, pins, receipt


def test_market_events_bronze_to_silver_chain(tmp_path: Path) -> None:
    bronze_path, silver_path, pins, receipt = _chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path), read_only=True) as reader,
    ):
        records = silver.read_market_events_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )
        assert len(records) == receipt["row_count"] == 4
        assert records == bronze_api.read_market_events_bronze(bronze_conn, **pins.reader_args())
        reader_pins = pins.reader_args()
        reader_pins.pop("expected_recording_fingerprint")
        assert records == silver.revalidate_market_events_silver(
            bronze_conn,
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
            expected_bronze_recording_fingerprint=pins.recording_fingerprint,
            **reader_pins,
        )
        rows = reader.execute(
            "SELECT event_id,source,event_type,title,description,symbol,event_ts,importance,"
            "consensus_value,actual_value,surprise_label,affected_underlyings,raw_payload,"
            "ingested_at FROM silver.market_event_observations WHERE revision_id=? ORDER BY ordinal",
            [receipt["revision_id"]],
        ).fetchall()
        by_key = {row[0]: row for row in rows}
        assert by_key["ev-1"][6] == AT and by_key["ev-1"][8] == 100.0
        assert by_key["ev-2"][1:] == (None,) * 13
        assert by_key["ev-3"][8] is None and by_key["ev-3"][11] == "[]"
        assert by_key["ev-4"][11] == "null" and by_key["ev-4"][12] == "[]"


@pytest.mark.parametrize(
    "column,value",
    [
        ("event_id", "'changed'"),
        ("source", "'changed'"),
        ("event_type", "'changed'"),
        ("title", "'changed'"),
        ("description", "'changed'"),
        ("symbol", "'changed'"),
        ("event_ts", "event_ts + INTERVAL '1 microsecond'"),
        ("importance", "'changed'"),
        ("consensus_value", "consensus_value + 0.5"),
        ("actual_value", "actual_value + 0.5"),
        ("surprise_label", "'changed'"),
        ("affected_underlyings", "'changed'"),
        ("raw_payload", "'changed'"),
        ("ingested_at", "ingested_at + INTERVAL '1 microsecond'"),
    ],
    ids=[
        "key",
        "source",
        "event-type",
        "title",
        "description",
        "symbol",
        "event-ts",
        "importance",
        "consensus-value",
        "actual-value",
        "surprise-label",
        "affected-underlyings",
        "raw-payload",
        "ingested-at",
    ],
)
def test_materialized_field_corruption_rejected(tmp_path: Path, column: str, value: str) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        changed = writer.execute(
            f"UPDATE silver.market_event_observations SET {column}={value} WHERE ordinal=0 RETURNING 1"
        ).fetchone()
        assert changed == (1,)
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError, match="MATERIALIZED_FIELD_MISMATCH"),
    ):
        silver.read_market_events_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_missing_row_rejected(tmp_path: Path) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("DELETE FROM silver.market_event_observations WHERE ordinal=0")
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError, match="ORDINAL_COVERAGE_MISMATCH"),
    ):
        silver.read_market_events_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_ordinal_gap_rejected(tmp_path: Path) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("UPDATE silver.market_event_observations SET ordinal=ordinal+10 WHERE ordinal=1")
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError, match="ORDINAL_COVERAGE_MISMATCH"),
    ):
        silver.read_market_events_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_market_events_silver_tampering(tmp_path: Path) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("UPDATE silver.market_event_sets SET context='bad'::BLOB")
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError),
    ):
        silver.read_market_events_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_market_events_silver_first_write_obligation(tmp_path: Path) -> None:
    bronze_path, silver_path, pins, receipt = _chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        context = silver.observe_market_events_bronze(bronze_conn, pins=pins)
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            silver.persist_market_events_silver(
                bronze_conn,
                target,
                pins=pins,
                expected_context_sha256=base.sha(context),
                actor_id="other",
                code_revision="b" * 40,
            )


def test_market_events_silver_same_file_alias(tmp_path: Path) -> None:
    _bronze_path, silver_path, pins, _receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as target:
        alias = target.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                silver.persist_market_events_silver(
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
