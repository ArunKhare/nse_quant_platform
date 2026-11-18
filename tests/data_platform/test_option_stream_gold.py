"""Tests for option-chain Gold feature set v1."""

from __future__ import annotations

import duckdb
import pytest

from nse_quant.data_platform.option_stream_gold import (
    build_option_chain_features,
    initialize_option_chain_gold,
)


def _setup(tmp_path):
    silver = duckdb.connect(str(tmp_path / "silver.duckdb"))
    target = duckdb.connect(str(tmp_path / "gold.duckdb"))
    silver.execute("CREATE SCHEMA silver.silver")
    silver.execute("""
        CREATE TABLE silver.silver.option_stream_revisions (
            revision_id VARCHAR PRIMARY KEY, bronze_snapshot_id VARCHAR NOT NULL,
            bronze_capture_event_id VARCHAR NOT NULL, bronze_envelope_hash VARCHAR NOT NULL,
            bronze_recording_fingerprint VARCHAR NOT NULL, bronze_source_label VARCHAR NOT NULL,
            context_sha256 VARCHAR NOT NULL, observation_count BIGINT NOT NULL,
            quarantined_count BIGINT NOT NULL, recorded_at TIMESTAMPTZ NOT NULL)
    """)
    silver.execute("""
        CREATE TABLE silver.silver.option_stream_observations (
            revision_id VARCHAR NOT NULL, source_ordinal BIGINT NOT NULL,
            bronze_snapshot_id VARCHAR NOT NULL, bronze_capture_event_id VARCHAR NOT NULL,
            bronze_envelope_hash VARCHAR NOT NULL, bronze_recording_fingerprint VARCHAR NOT NULL,
            bronze_source_label VARCHAR NOT NULL, ts TIMESTAMPTZ NOT NULL,
            underlying VARCHAR NOT NULL, expiry DATE, strike DOUBLE, option_type VARCHAR,
            tradingsymbol VARCHAR, instrument_token BIGINT, lot_size BIGINT, spot DOUBLE,
            ltp DOUBLE, bid DOUBLE, ask DOUBLE, volume BIGINT, oi BIGINT, iv DOUBLE,
            delta DOUBLE, gamma DOUBLE, vega DOUBLE, theta DOUBLE, quote_status VARCHAR,
            payload_json VARCHAR, quality_status VARCHAR NOT NULL, quality_reason VARCHAR,
            recorded_at TIMESTAMPTZ NOT NULL, PRIMARY KEY(revision_id,source_ordinal))
    """)
    initialize_option_chain_gold(target)
    return silver, target


def _insert_revision(silver, revision_id):
    silver.execute(
        "INSERT INTO silver.silver.option_stream_revisions VALUES (?,'s','c','e','f','l','x',2,0,now())",
        [revision_id],
    )
    for ordinal, kind, strike, iv, oi in ((0, "CE", 100.0, 0.2, 10), (1, "PE", 100.0, 0.22, 20)):
        silver.execute(
            """
            INSERT INTO silver.silver.option_stream_observations
            (revision_id,source_ordinal,bronze_snapshot_id,bronze_capture_event_id,
             bronze_envelope_hash,bronze_recording_fingerprint,bronze_source_label,ts,
             underlying,expiry,strike,option_type,tradingsymbol,instrument_token,lot_size,
             spot,ltp,bid,ask,volume,oi,iv,delta,gamma,vega,theta,quote_status,payload_json,
             quality_status,quality_reason,recorded_at)
            VALUES (?,?,?,?,?,?,?,?,?,NULL,?,?,NULL,NULL,NULL,100.0,1.0,1.0,1.0,0,?,?,NULL, \
            NULL,NULL,NULL,'missing','{}','VALID',NULL,now())
            """,
            [revision_id, ordinal, "s", "c", "e", "f", "l", "2026-01-01", "NIFTY", strike, kind, oi, iv],
        )


def test_builds_deterministic_features(tmp_path):
    silver, target = _setup(tmp_path)
    _insert_revision(silver, "a" * 64)
    receipt = build_option_chain_features(silver, target, actor_id="tester", code_revision="test")
    assert receipt["built"] == 1
    again = build_option_chain_features(silver, target, actor_id="tester", code_revision="test")
    assert again["built"] == 0
    row = target.execute("SELECT feature_context FROM gold.gold.option_chain_feature_sets").fetchone()
    assert row is not None
    assert b'"atm_iv"' in row[0]


def test_rejects_count_mismatch(tmp_path):
    silver, target = _setup(tmp_path)
    _insert_revision(silver, "b" * 64)
    silver.execute(
        "UPDATE silver.silver.option_stream_revisions SET observation_count=3 WHERE revision_id=?",
        ["b" * 64],
    )
    with pytest.raises(ValueError, match="SILVER_OBSERVATION_COUNT_MISMATCH"):
        build_option_chain_features(silver, target, actor_id="tester", code_revision="test")
