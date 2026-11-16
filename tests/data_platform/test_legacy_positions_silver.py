"""Actual positions writer -> Bronze -> persisted Silver chain."""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import legacy_positions as codec
from nse_quant.data_platform import legacy_positions_bronze as bronze_api
from nse_quant.data_platform import legacy_positions_silver_store as silver
from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore

AT = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
CLOSED_AT = datetime(2026, 1, 1, 15, 30, tzinfo=UTC)
EXPIRY = date(2026, 1, 29)
REVISION = "a" * 40
TABLE = '"main"."positions"'


def _seed(path: Path) -> None:
    writer = duckdb.connect(str(path))
    try:
        columns = ",".join(f'"{n}" {k}' for n, k in codec.SCHEMA)
        writer.execute(f'CREATE TABLE {TABLE} ({columns},PRIMARY KEY("position_id"))')
        writer.executemany(
            f"INSERT INTO {TABLE} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    "pos-1",
                    "sp-1",
                    "prop-1",
                    "swing",
                    "NIFTY",
                    EXPIRY,
                    "NIFTY25JAN24500CE",
                    123456,
                    "CE",
                    24500.0,
                    "LONG",
                    1,
                    75,
                    AT,
                    100.5,
                    105.5,
                    375.0,
                    0.0,
                    "OPEN",
                    None,
                    None,
                    False,
                ),
                (
                    "pos-2",
                    "sp-2",
                    "prop-1",
                    "swing",
                    "NIFTY",
                    EXPIRY,
                    "NIFTY25JAN24500PE",
                    123457,
                    "PE",
                    24500.0,
                    "SHORT",
                    1,
                    -75,
                    AT,
                    100.5,
                    95.5,
                    0.0,
                    375.0,
                    "CLOSED",
                    CLOSED_AT,
                    "target",
                    True,
                ),
                (
                    "pos-3",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
                (
                    "pos-4",
                    "sp-4",
                    "prop-2",
                    "swing",
                    "NIFTY",
                    None,
                    "NIFTY25JAN24600CE",
                    123458,
                    "CE",
                    24600.0,
                    "LONG",
                    2,
                    150,
                    AT,
                    50.0,
                    55.0,
                    None,
                    None,
                    "OPEN",
                    None,
                    None,
                    False,
                ),
            ],
        )
    finally:
        writer.close()


def _bronze(tmp_path: Path) -> tuple[Path, silver.PositionsBronzePins]:
    source_path, bronze_path = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    _seed(source_path)
    source = duckdb.connect(str(source_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = bronze_api.capture_positions(source, source_label="fixture")
        receipt = bronze_api.preserve_positions(
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
    return bronze_path, silver.PositionsBronzePins(
        source_label=receipt["source_label"],
        snapshot_id=receipt["snapshot_id"],
        capture_event_id=receipt["capture_event_id"],
        envelope_hash=receipt["envelope_hash"],
        recording_fingerprint=receipt["recording_fingerprint"],
    )


def _chain(tmp_path: Path) -> tuple[Path, Path, silver.PositionsBronzePins, dict[str, Any]]:
    bronze_path, pins = _bronze(tmp_path)
    silver_path = tmp_path / "positions_silver.duckdb"
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        silver.initialize_positions_silver(target)
        context = silver.observe_positions_bronze(bronze_conn, pins=pins)
        receipt = silver.persist_positions_silver(
            bronze_conn,
            target,
            pins=pins,
            expected_context_sha256=base.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver_path, pins, receipt


def test_positions_bronze_to_silver_chain(tmp_path: Path) -> None:
    bronze_path, silver_path, pins, receipt = _chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path), read_only=True) as reader,
    ):
        records = silver.read_positions_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )
        assert len(records) == receipt["row_count"] == 4
        assert records == bronze_api.read_positions_bronze(bronze_conn, **pins.reader_args())
        reader_pins = pins.reader_args()
        reader_pins.pop("expected_recording_fingerprint")
        assert records == silver.revalidate_positions_silver(
            bronze_conn,
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
            expected_bronze_recording_fingerprint=pins.recording_fingerprint,
            **reader_pins,
        )
        rows = reader.execute(
            "SELECT position_id,strategy_position_id,proposal_id,strategy,underlying,expiry,"
            "tradingsymbol,instrument_token,option_type,strike,side,lots,quantity,opened_at,"
            "entry_price,current_price,realized_pnl,unrealized_pnl,status,closed_at,"
            "exit_reason,mark_stale FROM silver.position_observations "
            "WHERE revision_id=? ORDER BY ordinal",
            [receipt["revision_id"]],
        ).fetchall()
        assert rows[0][0] == "pos-1" and rows[0][5] == EXPIRY and rows[0][9] == 24500.0
        assert rows[1][18] == "CLOSED" and rows[1][19] == CLOSED_AT and rows[1][21] is True
        assert rows[2][1:] == (None,) * 21
        assert rows[3][5] is None and rows[3][16] is None and rows[3][17] is None


@pytest.mark.parametrize(
    "column,value",
    [
        ("position_id", "'changed-key'"),
        ("strategy_position_id", "'changed'"),
        ("proposal_id", "'changed'"),
        ("strategy", "'changed'"),
        ("underlying", "'changed'"),
        ("expiry", "DATE '2026-02-01'"),
        ("tradingsymbol", "'changed'"),
        ("instrument_token", "999999"),
        ("option_type", "'changed'"),
        ("strike", "1.0"),
        ("side", "'changed'"),
        ("lots", "99"),
        ("quantity", "99"),
        ("opened_at", "TIMESTAMPTZ '2026-01-02 09:15:00+00'"),
        ("entry_price", "1.0"),
        ("current_price", "1.0"),
        ("realized_pnl", "1.0"),
        ("unrealized_pnl", "1.0"),
        ("status", "'changed'"),
        ("closed_at", "TIMESTAMPTZ '2026-01-02 09:15:00+00'"),
        ("exit_reason", "'changed'"),
        ("mark_stale", "TRUE"),
    ],
    ids=[
        "key",
        "strategy-position",
        "proposal",
        "strategy",
        "underlying",
        "expiry",
        "trading-symbol",
        "instrument-token",
        "option-type",
        "strike",
        "side",
        "lots",
        "quantity",
        "opened-at",
        "entry-price",
        "current-price",
        "realized-pnl",
        "unrealized-pnl",
        "status",
        "closed-at",
        "exit-reason",
        "mark-stale",
    ],
)
def test_materialized_field_corruption_rejected(tmp_path: Path, column: str, value: str) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute(f"UPDATE silver.position_observations SET {column}={value} WHERE ordinal=0")
        changed = writer.execute(
            f"UPDATE silver.position_observations SET {column}={value} WHERE ordinal=0 RETURNING 1"
        ).fetchone()
        assert changed == (1,)
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError, match="MATERIALIZED_FIELD_MISMATCH"),
    ):
        silver.read_positions_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_missing_row_rejected(tmp_path: Path) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("DELETE FROM silver.position_observations WHERE ordinal=0")
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError, match="ORDINAL_COVERAGE_MISMATCH"),
    ):
        silver.read_positions_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_ordinal_gap_rejected(tmp_path: Path) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("UPDATE silver.position_observations SET ordinal=ordinal+10 WHERE ordinal=1")
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError, match="ORDINAL_COVERAGE_MISMATCH"),
    ):
        silver.read_positions_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_positions_silver_tampering(tmp_path: Path) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("UPDATE silver.position_sets SET context='bad'::BLOB")
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError),
    ):
        silver.read_positions_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_positions_silver_first_write_obligation(tmp_path: Path) -> None:
    bronze_path, silver_path, pins, receipt = _chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        context = silver.observe_positions_bronze(bronze_conn, pins=pins)
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            silver.persist_positions_silver(
                bronze_conn,
                target,
                pins=pins,
                expected_context_sha256=base.sha(context),
                actor_id="other",
                code_revision="b" * 40,
            )


def test_positions_silver_same_file_alias(tmp_path: Path) -> None:
    _bronze_path, silver_path, pins, _receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as target:
        alias = target.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                silver.persist_positions_silver(
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
