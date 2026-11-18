"""Deterministic option-chain Gold features derived only from Silver observations.

Feature set v1 computes only directly available chain-level aggregates. Missing
inputs remain NULL. No gap filling, decision eligibility, publication, or live
trading authority is asserted.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import duckdb

from nse_quant.data_platform.audit import AuditLedger

VERSION = "option_chain_features@1"
COMMAND = "build.option_chain_features@1"
FEATURE_SETS = "option_chain_feature_sets"
FEATURE_OBSERVATIONS = "option_chain_feature_observations"
FEATURE_ATTEMPTS = "option_chain_feature_attempts"
REQUIRED_OBSERVATION_COLUMNS = {
    "revision_id",
    "source_ordinal",
    "ts",
    "underlying",
    "expiry",
    "strike",
    "option_type",
    "spot",
    "ltp",
    "bid",
    "ask",
    "volume",
    "oi",
    "iv",
    "quality_status",
    "bronze_snapshot_id",
    "bronze_capture_event_id",
    "bronze_envelope_hash",
    "bronze_recording_fingerprint",
    "bronze_source_label",
}
REQUIRED_REVISION_COLUMNS = {
    "revision_id",
    "bronze_snapshot_id",
    "bronze_capture_event_id",
    "bronze_envelope_hash",
    "bronze_recording_fingerprint",
    "bronze_source_label",
    "context_sha256",
    "observation_count",
    "quarantined_count",
    "recorded_at",
}


def _json_default(value: object) -> str:
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            raise ValueError("NAIVE_DATETIME_NOT_ALLOWED")
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    raise TypeError(f"UNSUPPORTED_JSON_TYPE:{type(value).__name__}")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=False,
        default=_json_default,
    ).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _pin(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _schema(conn: duckdb.DuckDBPyConnection) -> None:
    obs = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='silver' AND table_name='option_stream_observations'"
        ).fetchall()
    }
    rev = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='silver' AND table_name='option_stream_revisions'"
        ).fetchall()
    }
    if not obs >= REQUIRED_OBSERVATION_COLUMNS or not rev >= REQUIRED_REVISION_COLUMNS:
        raise ValueError("SILVER_OPTION_STREAM_SCHEMA_MISMATCH")


def _catalog(conn: duckdb.DuckDBPyConnection) -> str:
    row = conn.execute("SELECT current_catalog()").fetchone()
    if row is None:
        raise ValueError("CURRENT_CATALOG_UNAVAILABLE")
    return str(row[0])


def _qualify(conn: duckdb.DuckDBPyConnection, schema: str, table: str) -> str:
    return f'"{_catalog(conn)}"."{schema}"."{table}"'


def initialize_option_chain_gold(target: duckdb.DuckDBPyConnection) -> None:
    AuditLedger(target).initialize()
    catalog = _catalog(target)
    schema = f'"{catalog}"."gold"'
    target.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    sets_table = _qualify(target, "gold", FEATURE_SETS)
    observations_table = _qualify(target, "gold", FEATURE_OBSERVATIONS)
    attempts_table = _qualify(target, "gold", FEATURE_ATTEMPTS)
    target.execute(
        f"CREATE TABLE IF NOT EXISTS {sets_table} ("
        "feature_revision_id VARCHAR PRIMARY KEY,"
        "silver_revision_id VARCHAR NOT NULL UNIQUE,"
        "feature_context BLOB NOT NULL,"
        "feature_context_sha256 VARCHAR NOT NULL,"
        "recorded_at TIMESTAMPTZ NOT NULL)"
    )
    target.execute(
        f"CREATE TABLE IF NOT EXISTS {observations_table} ("
        "feature_revision_id VARCHAR NOT NULL,"
        "feature_ordinal BIGINT NOT NULL,"
        "feature_record BLOB NOT NULL,"
        "recorded_at TIMESTAMPTZ NOT NULL,"
        "PRIMARY KEY(feature_revision_id,feature_ordinal))"
    )
    target.execute(
        f"CREATE TABLE IF NOT EXISTS {attempts_table} ("
        "feature_revision_id VARCHAR PRIMARY KEY,"
        "job_id VARCHAR NOT NULL,"
        "recorded_at TIMESTAMPTZ NOT NULL)"
    )


def _feature_record(row: dict[str, Any]) -> dict[str, Any]:
    calls = [r for r in row["observations"] if r["option_type"] == "CE"]
    puts = [r for r in row["observations"] if r["option_type"] == "PE"]
    spot = row["spot"]
    atm_call = None
    atm_put = None
    if spot is not None:

        def nearest(items: list[dict[str, Any]]) -> dict[str, Any] | None:
            usable = [r for r in items if r["strike"] is not None]
            return min(usable, key=lambda r: abs(r["strike"] - spot)) if usable else None

        atm_call = nearest(calls)
        atm_put = nearest(puts)
    call_oi = sum(r["oi"] or 0 for r in calls)
    put_oi = sum(r["oi"] or 0 for r in puts)
    pcr = put_oi / call_oi if call_oi else None
    atm_iv = None
    if atm_call and atm_call["iv"] is not None:
        atm_iv = atm_call["iv"]
    elif atm_put and atm_put["iv"] is not None:
        atm_iv = atm_put["iv"]
    straddle = None
    expected_move = None
    if atm_call and atm_put and atm_call["ltp"] is not None and atm_put["ltp"] is not None:
        straddle = atm_call["ltp"] + atm_put["ltp"]
        if spot:
            expected_move = straddle / spot
    return {
        "version": VERSION,
        "ts": row["ts"],
        "underlying": row["underlying"],
        "expiry": row["expiry"],
        "spot": spot,
        "atm_strike": atm_call["strike"] if atm_call else (atm_put["strike"] if atm_put else None),
        "atm_iv": atm_iv,
        "pcr": pcr,
        "call_oi": call_oi,
        "put_oi": put_oi,
        "total_volume": sum(r["volume"] or 0 for r in row["observations"]),
        "straddle": straddle,
        "expected_move": expected_move,
        "observation_count": len(row["observations"]),
        "quality_status": row["quality_status"],
        "decision_eligibility_asserted": False,
    }


def build_option_chain_features(
    silver: duckdb.DuckDBPyConnection,
    target: duckdb.DuckDBPyConnection,
    *,
    actor_id: str,
    code_revision: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    if not actor_id.strip() or not code_revision.strip():
        raise ValueError("ACTOR_AND_CODE_REVISION_REQUIRED")
    _schema(silver)
    rev_table = _qualify(silver, "silver", "option_stream_revisions")
    obs_table = _qualify(silver, "silver", "option_stream_observations")
    sets_table = _qualify(target, "gold", FEATURE_SETS)
    feat_obs_table = _qualify(target, "gold", FEATURE_OBSERVATIONS)
    attempts_table = _qualify(target, "gold", FEATURE_ATTEMPTS)
    filters = []
    params: list[object] = []
    if start_date:
        filters.append("CAST(r.recorded_at AT TIME ZONE 'Asia/Kolkata' AS DATE) >= ?")
        params.append(start_date)
    if end_date:
        filters.append("CAST(r.recorded_at AT TIME ZONE 'Asia/Kolkata' AS DATE) <= ?")
        params.append(end_date)
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    revisions = silver.execute(
        f"""
        SELECT revision_id, bronze_snapshot_id, bronze_capture_event_id,
               bronze_envelope_hash, bronze_recording_fingerprint, bronze_source_label,
               context_sha256, observation_count, quarantined_count, recorded_at
        FROM {rev_table} r
        {where}
        ORDER BY recorded_at, revision_id
        """,
        params,
    ).fetchall()
    built = 0
    ledger = AuditLedger(target)
    for revision in revisions:
        (
            revision_id,
            snapshot_id,
            capture_event_id,
            envelope_hash,
            recording_fingerprint,
            source_label,
            context_sha256,
            observation_count,
            quarantined_count,
            recorded_at,
        ) = revision
        feature_revision_id = _sha(
            _canonical(
                [
                    VERSION,
                    revision_id,
                    context_sha256,
                    recording_fingerprint,
                ]
            )
        )
        existing = target.execute(
            f"SELECT 1 FROM {sets_table} WHERE silver_revision_id=? LIMIT 1",
            [revision_id],
        ).fetchone()
        if existing:
            continue
        observations = silver.execute(
            f"""
            SELECT source_ordinal, ts, underlying, expiry, strike, option_type,
                   spot, ltp, bid, ask, volume, oi, iv, quality_status
            FROM {obs_table}
            WHERE revision_id=?
            ORDER BY source_ordinal
            """,
            [revision_id],
        ).fetchall()
        if len(observations) != observation_count:
            raise ValueError("SILVER_OBSERVATION_COUNT_MISMATCH")
        names = [
            "source_ordinal",
            "ts",
            "underlying",
            "expiry",
            "strike",
            "option_type",
            "spot",
            "ltp",
            "bid",
            "ask",
            "volume",
            "oi",
            "iv",
            "quality_status",
        ]
        rows = [dict(zip(names, row, strict=True)) for row in observations]
        feature = _feature_record(
            {
                "observations": rows,
                "spot": rows[0]["spot"] if rows else None,
                "ts": rows[0]["ts"] if rows else None,
                "underlying": rows[0]["underlying"] if rows else None,
                "expiry": rows[0]["expiry"] if rows else None,
                "quality_status": "VALID" if quarantined_count == 0 else "QUARANTINED",
            }
        )
        context = _canonical(
            {
                "version": VERSION,
                "silver_revision_id": revision_id,
                "silver_context_sha256": context_sha256,
                "bronze_pins": {
                    "snapshot_id": snapshot_id,
                    "capture_event_id": capture_event_id,
                    "envelope_hash": envelope_hash,
                    "recording_fingerprint": recording_fingerprint,
                    "source_label": source_label,
                },
                "feature": feature,
            }
        )
        job = ledger.plan_job(
            command_name=COMMAND,
            actor_id=actor_id,
            code_revision=code_revision,
            scope_ref="sha256:" + feature_revision_id,
            config_hash=_sha(context),
        )
        with ledger.execution(job):
            target.execute("BEGIN TRANSACTION")
            try:
                target.execute(
                    f"INSERT INTO {sets_table} VALUES (?,?,?,?,?)",
                    [feature_revision_id, revision_id, context, _sha(context), datetime.now(UTC)],
                )
                target.execute(
                    f"INSERT INTO {feat_obs_table} VALUES (?,?,?,?)",
                    [feature_revision_id, 0, context, datetime.now(UTC)],
                )
                target.execute(
                    f"INSERT INTO {attempts_table} VALUES (?,?,?)",
                    [feature_revision_id, job, datetime.now(UTC)],
                )
                target.execute("COMMIT")
            except BaseException:
                target.execute("ROLLBACK")
                raise
        built += 1
    return {"built": built, "total_silver_revisions": len(revisions), "feature_set": VERSION}
