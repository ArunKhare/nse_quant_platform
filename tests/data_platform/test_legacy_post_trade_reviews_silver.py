"""Actual post-trade-reviews writer -> Bronze -> persisted Silver chain."""

from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.core.models import ExitReason, PostTradeReview
from nse_quant.data_platform import legacy_post_trade_reviews_bronze as bronze_api
from nse_quant.data_platform import legacy_post_trade_reviews_silver_store as silver
from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.persistence.repositories import PositionRepository

AT = datetime(2026, 1, 1, 16, 0, tzinfo=UTC)
REVISION = "a" * 40


def seed(path):
    legacy = DuckDBStore(path=path)
    try:
        repository = PositionRepository(legacy.conn)
        repository.save_post_trade_review(
            PostTradeReview(
                review_id="review-1",
                strategy_position_id="sp-1",
                proposal_id="prop-1",
                strategy="strat-1",
                closed_at=AT,
                realized_pnl=375.0,
                exit_reason=ExitReason.IV_COLLAPSE,
                thesis_status="VALID",
                decision_quality_notes="clean entry",
                outcome_notes="positive",
            )
        )
        repository.save_post_trade_review(
            PostTradeReview(
                review_id="review-2",
                strategy_position_id="sp-2",
                proposal_id="prop-1",
                strategy="strat-1",
                closed_at=AT,
                realized_pnl=-50.0,
                exit_reason=ExitReason.STOP_LOSS,
                thesis_status="INVALID",
                decision_quality_notes="",
                outcome_notes="",
            )
        )
        table = bronze_api.common.name(legacy.conn, "main", bronze_api.codec.TABLE)
        legacy.conn.execute(
            f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?,?,?)",
            ["review-3", None, None, None, None, None, None, None, None, None],
        )
    finally:
        legacy.close()


def bronze(tmp_path):
    legacy_path, bronze_path = tmp_path / "legacy.duckdb", tmp_path / "bronze.duckdb"
    seed(legacy_path)
    with (
        duckdb.connect(str(legacy_path), read_only=True) as source,
        duckdb.connect(str(bronze_path)) as target,
    ):
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = bronze_api.capture_post_trade_reviews(source, source_label="fixture")
        result = bronze_api.preserve_post_trade_reviews(
            source,
            target,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver.PostTradeReviewsBronzePins(
        source_label=result["source_label"],
        snapshot_id=result["snapshot_id"],
        capture_event_id=result["capture_event_id"],
        envelope_hash=result["envelope_hash"],
        recording_fingerprint=result["recording_fingerprint"],
    )


def chain(tmp_path):
    bronze_path, pins = bronze(tmp_path)
    silver_path = tmp_path / "post_trade_reviews_silver.duckdb"
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        silver.initialize_post_trade_reviews_silver(target)
        context = silver.observe_post_trade_reviews_bronze(bronze_conn, pins=pins)
        receipt = silver.persist_post_trade_reviews_silver(
            bronze_conn,
            target,
            pins=pins,
            expected_context_sha256=base.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    return bronze_path, silver_path, pins, receipt


def test_post_trade_reviews_bronze_to_silver_chain(tmp_path):
    bronze_path, silver_path, pins, receipt = chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path), read_only=True) as reader,
    ):
        records = silver.read_post_trade_reviews_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )
        assert len(records) == receipt["row_count"] == 3
        assert records == bronze_api.read_post_trade_reviews_bronze(
            bronze_conn, **pins.reader_args()
        )
        assert records == silver.revalidate_post_trade_reviews_silver(
            bronze_conn,
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
            source_label=pins.source_label,
            snapshot_id=pins.snapshot_id,
            capture_event_id=pins.capture_event_id,
            envelope_hash=pins.envelope_hash,
            expected_bronze_recording_fingerprint=pins.recording_fingerprint,
        )
        rows = reader.execute(
            "SELECT review_id,ts,strategy_position_id,proposal_id,strategy,realized_pnl,"
            "exit_reason,thesis_status,decision_quality_notes,outcome_notes "
            "FROM silver.post_trade_review_observations WHERE revision_id=? ORDER BY ordinal",
            [receipt["revision_id"]],
        ).fetchall()
        assert rows[0][0] == "review-1" and rows[0][1].tzinfo is not None
        assert rows[0][5] == 375.0 and rows[0][7] == "VALID"
        assert rows[1][5] == -50.0 and rows[1][8] == "" and rows[1][9] == ""
        assert rows[2][1:] == (None,) * 9


def test_post_trade_reviews_silver_tampering(tmp_path):
    _b, silver_path, _pins, receipt = chain(tmp_path)
    with duckdb.connect(str(silver_path)) as writer:
        writer.execute("UPDATE silver.post_trade_review_sets SET context='bad'::BLOB")
    with duckdb.connect(str(silver_path), read_only=True) as reader, pytest.raises(ValueError):
        silver.read_post_trade_reviews_silver(
            reader,
            revision_id=receipt["revision_id"],
            expected_recording_fingerprint=receipt["recording_fingerprint"],
        )


def test_post_trade_reviews_silver_first_write_obligation(tmp_path):
    bronze_path, silver_path, pins, receipt = chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
        duckdb.connect(str(silver_path)) as target,
    ):
        context = silver.observe_post_trade_reviews_bronze(bronze_conn, pins=pins)
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            silver.persist_post_trade_reviews_silver(
                bronze_conn,
                target,
                pins=pins,
                expected_context_sha256=base.sha(context),
                actor_id="other",
                code_revision="b" * 40,
            )


def test_post_trade_reviews_silver_same_file_alias(tmp_path):
    bronze_path, silver_path, pins, receipt = chain(tmp_path)
    with (
        duckdb.connect(str(bronze_path), read_only=True),
        duckdb.connect(str(silver_path)) as target,
    ):
        alias = target.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                silver.persist_post_trade_reviews_silver(
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
