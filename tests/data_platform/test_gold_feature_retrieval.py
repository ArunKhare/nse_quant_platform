"""Tests for availability-aware Gold feature retrieval and exact replay."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform.gold_feature_retrieval import (
    replay_gold_feature,
    retrieve_gold_feature,
)


def _setup(tmp_path):
    gold = duckdb.connect(str(tmp_path / "gold.duckdb"))
    gold.execute("CREATE SCHEMA gold.gold")
    gold.execute("CREATE SCHEMA medallion_audit")
    gold.execute("""
        CREATE TABLE gold.gold.option_chain_feature_sets (
            feature_revision_id VARCHAR PRIMARY KEY,
            silver_revision_id VARCHAR NOT NULL UNIQUE,
            feature_context BLOB NOT NULL,
            feature_context_sha256 VARCHAR NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL)
    """)
    gold.execute("""
        CREATE TABLE gold.gold.option_chain_feature_observations (
            feature_revision_id VARCHAR PRIMARY KEY,
            feature_ordinal BIGINT NOT NULL,
            feature_record BLOB NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL)
    """)
    return gold


def _insert(gold, revision):
    context = json.dumps(
        {
            "version": "option_chain_features@1",
            "silver_revision_id": "a" * 64,
            "silver_context_sha256": "b" * 64,
            "bronze_pins": {
                "snapshot_id": "c" * 64,
                "capture_event_id": "d" * 64,
                "envelope_hash": "e" * 64,
                "recording_fingerprint": "f" * 64,
                "source_label": "legacy",
            },
            "feature": {
                "version": "option_chain_features@1",
                "underlying": "NIFTY",
                "decision_eligibility_asserted": False,
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    feature_revision = (
        __import__("hashlib")
        .sha256(
            __import__("json")
            .dumps(["option_chain_features@1", "a" * 64, "b" * 64, "f" * 64], sort_keys=True, separators=(",", ":"))
            .encode()
        )
        .hexdigest()
    )
    gold.execute(
        "INSERT INTO gold.gold.option_chain_feature_sets VALUES (?,?,?,?,?)",
        [
            feature_revision,
            "a" * 64,
            context,
            __import__("hashlib").sha256(context).hexdigest(),
            datetime(2026, 1, 2, tzinfo=UTC),
        ],
    )
    gold.execute(
        "INSERT INTO gold.gold.option_chain_feature_observations VALUES (?,0,?,?)",
        [feature_revision, context, datetime(2026, 1, 2, tzinfo=UTC)],
    )
    return feature_revision


def test_retrieval_available_and_replay(tmp_path):
    gold = _setup(tmp_path)
    revision = _insert(gold, "a" * 64)
    receipt = retrieve_gold_feature(gold, underlying="NIFTY", as_of=datetime(2026, 1, 3, tzinfo=UTC))
    assert receipt["status"] == "FEATURE_AVAILABLE"
    assert receipt["bundle"]["feature_revision_id"] == revision
    replayed = replay_gold_feature(
        gold,
        bundle=receipt["bundle"],
        expected_bundle_sha256=receipt["bundle_sha256"],
    )
    assert replayed["status"] == "REPLAYED"
    assert replayed["feature_revision_id"] == revision


def test_retrieval_before_availability(tmp_path):
    gold = _setup(tmp_path)
    _insert(gold, "a" * 64)
    receipt = retrieve_gold_feature(gold, underlying="NIFTY", as_of=datetime(2026, 1, 1, tzinfo=UTC))
    assert receipt["status"] == "FEATURE_NOT_AVAILABLE"


def test_rejects_naive_time(tmp_path):
    gold = _setup(tmp_path)
    with pytest.raises(ValueError, match="AWARE_DECISION_TIME_REQUIRED"):
        retrieve_gold_feature(gold, underlying="NIFTY", as_of=datetime(2026, 1, 1))
