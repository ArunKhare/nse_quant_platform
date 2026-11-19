"""Native option-chain snapshot Bronze -> Silver chain."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform import native_option_chain_snapshot as codec
from nse_quant.data_platform import native_option_chain_snapshot_bronze as bronze_api
from nse_quant.data_platform import native_option_chain_snapshot_silver as silver
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore

AT = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
REVISION = "a" * 40


def _document() -> dict:
    def quote(token: int, symbol: str, strike: float, option_type: str) -> dict:
        return dict(
            instrument=dict(
                tradingsymbol=symbol,
                instrument_token=token,
                underlying="NIFTY",
                expiry=AT.date().isoformat(),
                strike=strike,
                option_type=option_type,
                lot_size=75,
            ),
            ltp=100.0,
            bid=99.5,
            ask=100.5,
            volume=1000,
            oi=500,
            exchange_ts=AT.isoformat(),
            trade_ts=AT.isoformat(),
            received_at=AT.isoformat(),
        )

    return dict(
        ts=AT.isoformat(),
        underlying="NIFTY",
        spot=25000.0,
        expiry=AT.date().isoformat(),
        is_market_open=True,
        quotes=[
            quote(1, "NIFTY-CE", 25100.0, "CE"),
            quote(2, "NIFTY-PE", 24900.0, "PE"),
        ],
    )


def _chain(tmp_path: Path) -> tuple[Path, Path, Any, Any]:
    bronze_path = tmp_path / "bronze.duckdb"
    silver_path = tmp_path / "option_chain_silver.duckdb"
    payload = codec.make_snapshot("fixture", _document())
    snapshot = codec.snapshot_id(payload)
    with duckdb.connect(str(bronze_path)) as bronze_conn:
        AuditLedger(bronze_conn).initialize()
        BronzeEventStore(bronze_conn).initialize()
        receipt = bronze_api.preserve_option_chain_snapshot(
            bronze_conn,
            source_label="fixture",
            payload=payload,
            expected_snapshot_id=snapshot,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
            origin_kind="historical_import",
        )
    pins = base.SilverPins(
        source_label=receipt["source_label"],
        snapshot_id=receipt["snapshot_id"],
        capture_event_id=receipt["capture_event_id"],
        envelope_hash=receipt["envelope_hash"],
        recording_fingerprint=receipt["recording_fingerprint"],
    )
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        silver.initialize_option_chain_snapshot_silver(target)
        context = silver.observe_option_chain_snapshot_bronze(bronze_conn, pins=pins)
        receipt = silver.persist_option_chain_snapshot_silver(
            bronze_conn,
            target,
            pins=pins,
            expected_context_sha256=base.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver_path, pins, receipt


def test_option_chain_bronze_to_silver_chain(tmp_path: Path) -> None:
    bronze_path, silver_path, pins, receipt = _chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path), read_only=True) as reader,
    ):
        records = silver.read_option_chain_snapshot_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )
        assert len(records) == receipt["row_count"] == 2
        assert records == bronze_api.read_option_chain_snapshot_bronze(bronze_conn, **pins.reader_args())
        revalidate_args = pins.reader_args()
        revalidate_args["revision_id"] = receipt["revision_id"]
        revalidate_args["expected_recording_fingerprint"] = receipt["recording_fingerprint"]
        revalidate_args["recording_fingerprint"] = pins.recording_fingerprint
        assert records == silver.revalidate_option_chain_snapshot_silver(bronze_conn, reader, **revalidate_args)


def test_option_chain_silver_tampering(tmp_path: Path) -> None:
    _b, silver_path, _pins, receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("UPDATE silver.option_chain_snapshot_sets SET context='bad'::BLOB")
    with (
        duckdb.connect(str(silver_path), read_only=True) as reader,
        pytest.raises(ValueError),
    ):
        silver.read_option_chain_snapshot_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_option_chain_silver_first_write_obligation(tmp_path: Path) -> None:
    bronze_path, silver_path, pins, receipt = _chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        context = silver.observe_option_chain_snapshot_bronze(bronze_conn, pins=pins)
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            silver.persist_option_chain_snapshot_silver(
                bronze_conn,
                target,
                pins=pins,
                expected_context_sha256=base.sha(context),
                actor_id="other",
                code_revision="b" * 40,
            )


def test_option_chain_silver_same_file_alias(tmp_path: Path) -> None:
    _bronze_path, silver_path, pins, _receipt = _chain(tmp_path)
    with duckdb.connect(str(silver_path)) as target:
        alias = target.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                silver.persist_option_chain_snapshot_silver(
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


def test_option_chain_codec_rejects_bad_document() -> None:
    with pytest.raises(ValueError):
        codec.make_snapshot("fixture", {"ts": "bad"})
