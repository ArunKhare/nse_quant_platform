"""Actual materialization-backed feature retrieval; temporary files only.

Supplied for checkout execution; not part of isolated kernel validation.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import duckdb
import pytest

from nse_quant.analytics import s2_iv30_history as history
from nse_quant.data_platform import s2_iv30_feature_reader as reader
from nse_quant.data_platform import s2_series_materialization as series

REVISION = "a" * 40
OBSERVATION = "b" * 64


def eod_case(tmp_path):
    now = datetime.now(UTC)
    selected = min(now.date(), now.astimezone(ZoneInfo("Asia/Kolkata")).date()) - timedelta(days=1)
    lines = ["date,close"] + [f"{selected - timedelta(days=120 - index)},{10 + index / 100}" for index in range(121)]
    csv = ("\n".join(lines) + "\n").encode()
    raw = history.build_history(
        raw_csv=csv,
        expected_raw_sha256=series.sha(csv),
        source_reference="synthetic-eod",
        received_at=(now - timedelta(seconds=1)).isoformat(),
        as_of=now.isoformat(),
        date_column="date",
        close_column="close",
    )
    materialized = series.prepare_eod(raw)
    path = tmp_path / "materialized.duckdb"
    with duckdb.connect(str(path)) as conn:
        series.initialize(conn, actor_id="fixture", code_revision=REVISION)
        series.persist(
            conn,
            raw=materialized,
            observation_id=OBSERVATION,
            expected_sha256=series.sha(materialized),
            actor_id="fixture",
            code_revision=REVISION,
        )
    return path, selected.isoformat(), materialized, now


def test_eod_feature_from_actual_audited_materialization_is_readonly(tmp_path):
    path, day, raw, _ = eod_case(tmp_path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with duckdb.connect(str(path), read_only=True) as conn:
        result = json.loads(
            reader.read_eod_feature(
                conn,
                observation_id=OBSERVATION,
                expected_sha256=series.sha(raw),
                trade_date=day,
                as_of=(datetime.now(UTC) + timedelta(seconds=1)).isoformat(),
            )
        )
    assert result["prior_observation_count"] == 120
    assert result["iv_percentile"] == pytest.approx(100)
    assert not result["decision_eligibility_asserted"]
    assert result["provenance"]["materialization_sha256"] == series.sha(raw)
    assert before == hashlib.sha256(path.read_bytes()).hexdigest()


def test_history_cannot_be_used_before_parent_materialization_audit_success(tmp_path):
    path, day, raw, before_write = eod_case(tmp_path)
    with duckdb.connect(str(path), read_only=True) as conn, pytest.raises(ValueError, match="NOT_YET_AVAILABLE"):
        reader.read_eod_feature(
            conn,
            observation_id=OBSERVATION,
            expected_sha256=series.sha(raw),
            trade_date=day,
            as_of=before_write.isoformat(),
        )


def test_conflicted_parent_cannot_produce_feature(tmp_path):
    path, day, raw, _ = eod_case(tmp_path)
    doc = json.loads(raw)
    request = dict(doc["content"]["request"])
    request["raw_csv"] = bytes.fromhex(request.pop("raw_csv_hex"))
    request["source_reference"] = "competing-interpretation"
    changed = series.prepare_eod(history.build_history(**request))
    with duckdb.connect(str(path)) as conn:
        assert series.persist(
            conn,
            raw=changed,
            observation_id=OBSERVATION,
            expected_sha256=series.sha(changed),
            actor_id="fixture",
            code_revision=REVISION,
        )["conflicted"]
    with duckdb.connect(str(path), read_only=True) as conn, pytest.raises(ValueError, match="CONFLICTED"):
        reader.read_eod_feature(
            conn,
            observation_id=OBSERVATION,
            expected_sha256=series.sha(raw),
            trade_date=day,
            as_of=(datetime.now(UTC) + timedelta(seconds=1)).isoformat(),
        )


def test_live_feature_uses_native_quote_clocks_and_retained_parent(tmp_path, monkeypatch):
    import test_s2_series_materialization_native as native

    monkeypatch.setattr(native, "AT", datetime.now(UTC) - timedelta(seconds=180))
    case = native.native_case(tmp_path)
    raw, _ = native.prepare_and_persist(case)
    bp, sp, target, _ = case
    with (
        duckdb.connect(str(bp), read_only=True) as bronze,
        duckdb.connect(str(sp), read_only=True) as silver,
        duckdb.connect(str(target), read_only=True) as materializations,
    ):
        result = json.loads(
            reader.read_live_feature(
                materializations,
                bronze,
                silver,
                observation_id=OBSERVATION,
                expected_sha256=series.sha(raw),
                as_of=(datetime.now(UTC) + timedelta(seconds=1)).isoformat(),
                max_age_seconds=300,
            )
        )
    assert result["iv30"] == pytest.approx(0.15)
    assert result["age_seconds"] >= 50
    assert not result["decision_eligibility_asserted"]
