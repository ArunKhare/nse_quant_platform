"""Offline reviewed S2 observations; append-only, no Gold or entry authority.

Writer is exclusively owned by caller. Audit commits are separate from domain
commits; interrupted writes create review obligations, never automatic healing.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform import india_vix_recording as common
from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform import native_surface_recording as native
from nse_quant.data_platform.audit import AuditLedger

VERSION = "s2-reviewed-observation-journal@1"
COMMAND = "persist.s2_reviewed_observation@1"
TABLE = "silver.s2_reviewed_observations"
MAX_BYTES = 12 * 1024 * 1024
MAX_VARIANTS = 64


def _request(request: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    raw = common.canonical(request)
    if not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("S2_REQUEST_BYTE_BOUND")
    value = json.loads(raw)
    if set(value) != {"snapshots", "artifacts", "policy"}:
        raise ValueError("S2_EXACT_REQUEST_FIELDS_REQUIRED")
    snapshots = value["snapshots"]
    if (
        type(snapshots) is not list
        or not 1 <= len(snapshots) <= 16
        or any(type(p) is not dict or set(p) != native.PIN_FIELDS for p in snapshots)
    ):
        raise ValueError("S2_EXACT_SNAPSHOT_PINS_REQUIRED")
    if len({p["snapshot_id"] for p in snapshots}) != len(snapshots):
        raise ValueError("S2_DUPLICATE_SNAPSHOT")
    if any(not base.pin(p[k]) for p in snapshots for k in native.PIN_FIELDS - {"source_label"}):
        raise ValueError("S2_EXACT_SNAPSHOT_PINS_REQUIRED")
    artifacts = value["artifacts"]
    if type(artifacts) is not dict or set(artifacts) != {"calendar", "forward", "rate"}:
        raise ValueError("S2_EXACT_ARTIFACT_SET_REQUIRED")
    for kind, pair in artifacts.items():
        if type(pair) is not list or len(pair) != 2 or not base.pin(pair[1]):
            raise ValueError("S2_ARTIFACT_ENCODING_REQUIRED")
        body = bytes.fromhex(pair[0])
        native._artifact(body, pair[1], kind)
    return raw, value


def request_bytes(*, snapshots, artifacts, policy) -> bytes:
    """Retain artifact bytes and exact pins, not caller-projected premium rows."""
    return _request(
        dict(snapshots=snapshots, artifacts={k: [raw.hex(), pin] for k, (raw, pin) in artifacts.items()}, policy=policy)
    )[0]


def _assemble(bronze: Any, doc: dict[str, Any]) -> bytes:
    """Explicit reviewed cohort with bounded capture-time skew, not equal clocks."""
    artifacts = {k: (bytes.fromhex(pair[0]), pair[1]) for k, pair in doc["artifacts"].items()}
    parts = {kind: native._artifact(raw, pin, kind) for kind, (raw, pin) in artifacts.items()}
    policy = doc["policy"]
    at = native._clock(policy["as_of"])
    closes = {}
    for text in parts["calendar"]["closes"]:
        day = native._clock(text).astimezone(native.IST).date().isoformat()
        if day in closes:
            raise ValueError("AMBIGUOUS_EXPIRY_DATE")
        closes[day] = text
    forwards, rates = parts["forward"], parts["rate"]
    if set(rates) != {row["expiry_close"] for row in forwards}:
        raise ValueError("FORWARD_RATE_COVERAGE_MISMATCH")
    if any(set(row) != {"expiry_close", "kind", "evidence"} for row in forwards):
        raise ValueError("FORWARD_ARTIFACT_FIELDS_MISMATCH")
    forwards = [dict(row, rate=rates[row["expiry_close"]]) for row in forwards]
    ordered = sorted(doc["snapshots"], key=lambda pin: pin["snapshot_id"])
    batch = base.sha(common.canonical(ordered))
    premiums, times, underlyings = [], [], set()
    seen_expiries: dict[str, str] = {}
    for pins in ordered:
        for raw in native.read_option_chain_snapshot_bronze(bronze, **pins):
            row = json.loads(raw)["stored_fields"]
            quote = row["quote"]
            inst = quote["instrument"]
            stamp = native._clock(row["ts"])
            times.append(stamp)
            underlyings.add(row["underlying"])
            expiry = row["expiry"]
            previous = seen_expiries.setdefault(expiry, pins["snapshot_id"])
            if previous != pins["snapshot_id"]:
                raise ValueError("DUPLICATE_NATIVE_EXPIRY_SNAPSHOT")
            if (
                stamp > at
                or expiry != inst["expiry"]
                or expiry not in closes
                or row["underlying"] != inst["underlying"]
            ):
                raise ValueError("NATIVE_SNAPSHOT_COHORT_MISMATCH")
            source = quote["exchange_ts"] or quote["trade_ts"]
            if source is None or quote["bid"] is None or quote["ask"] is None:
                raise ValueError("NATIVE_QUOTE_CLOCKS_AND_PREMIUM_REQUIRED")
            premiums.append(
                dict(
                    token=inst["instrument_token"],
                    underlying=row["underlying"],
                    batch_id=batch,
                    expiry_close=closes[expiry],
                    strike=inst["strike"],
                    option_type=inst["option_type"],
                    bid=quote["bid"],
                    ask=quote["ask"],
                    source_time=source,
                    received_at=quote["received_at"],
                )
            )
            if len(premiums) > native.bundle.MAX_QUOTES:
                raise ValueError("PREMIUM_COUNT_BOUND")
    gap = policy["max_source_gap_seconds"]
    if (
        not times
        or len(underlyings) != 1
        or isinstance(gap, bool)
        or not isinstance(gap, (int, float))
        or not math.isfinite(gap)
        or gap < 0
        or (max(times) - min(times)).total_seconds() > gap
    ):
        raise ValueError("NATIVE_SNAPSHOT_COHORT_MISMATCH")
    evidence = dict(policy=policy, calendar=parts["calendar"], forwards=forwards, premiums=premiums)
    return common.canonical(
        dict(
            version=VERSION,
            snapshots=ordered,
            artifacts=doc["artifacts"],
            policy=policy,
            bundle=json.loads(native.bundle.build_bundle(evidence)),
        )
    )


def observe(bronze: Any, request: bytes) -> bytes:
    """Verify native provenance first; then retain deterministic quality rejection.

    SQL/I/O failures and source provenance failures propagate, not quality records.
    """
    base.readonly(bronze)
    if type(request) is not bytes or not 0 < len(request) <= MAX_BYTES:
        raise ValueError("S2_REQUEST_BYTE_BOUND")
    checked, doc = _request(json.loads(request))
    if checked != request:
        raise ValueError("S2_CANONICAL_REQUEST_REQUIRED")
    for pins in doc["snapshots"]:
        native.read_option_chain_snapshot_bronze(bronze, **pins)
    quality: str
    record: dict[str, Any] | None
    reason: str | None
    try:
        assembled = _assemble(bronze, doc)
    except (ValueError, KeyError, TypeError, OverflowError):
        quality, record, reason = "rejected", None, "SURFACE_INPUTS_REJECTED"
    else:
        quality, record, reason = "valid_observation", json.loads(assembled), None
    body = common.canonical(
        dict(
            version=VERSION,
            request=doc,
            quality_state=quality,
            rejection_reason=reason,
            record=record,
            decision_eligibility_asserted=False,
        )
    )
    if len(body) > MAX_BYTES:
        raise ValueError("S2_OBSERVATION_BYTE_BOUND")
    return body


def initialize(target: Any, *, actor_id: str, code_revision: str) -> None:
    common.execution(actor_id, code_revision)
    common.silver_target(target)
    AuditLedger(target).initialize()
    table = common.table(target, TABLE)
    schema = table.rsplit(".", 1)[0]
    target.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    target.execute(
        f"CREATE TABLE IF NOT EXISTS {table} ("
        "scope VARCHAR NOT NULL, digest VARCHAR NOT NULL, body BLOB NOT NULL, "
        "job_id VARCHAR NOT NULL UNIQUE, recorded_at TIMESTAMPTZ NOT NULL, "
        "PRIMARY KEY(scope,digest))"
    )


def _rows(conn: Any, scope: str):
    table = common.table(conn, TABLE)
    rows = conn.execute(
        f"SELECT digest, CASE WHEN octet_length(body)<=? THEN body END, "
        f"job_id,recorded_at FROM {table} WHERE scope=? ORDER BY digest LIMIT ?",
        [MAX_BYTES, scope, MAX_VARIANTS + 1],
    ).fetchall()
    if len(rows) > MAX_VARIANTS:
        raise ValueError("S2_VARIANT_BOUND")
    return rows


def _verify(conn: Any, scope: str):
    rows = _rows(conn, scope)
    jobs = common.table(conn, "medallion_audit.jobs")
    ledger_rows = conn.execute(
        f"SELECT job_id,config_hash FROM {jobs} WHERE command_name=? AND scope_ref=? LIMIT ?",
        [COMMAND, scope, MAX_VARIANTS + 1],
    ).fetchall()
    if (
        len(ledger_rows) != len(rows)
        or len(ledger_rows) > MAX_VARIANTS
        or {(r[0], r[1]) for r in ledger_rows} != {(r[2], r[0]) for r in rows}
    ):
        raise ValueError("S2_ORPHAN_OR_INTERRUPTED_AUDIT_REQUIRES_REVIEW")
    for digest, body, job, recorded_at in rows:
        if body is None or base.sha(bytes(body)) != digest:
            raise ValueError("S2_RECORD_INTEGRITY_MISMATCH")
        doc = json.loads(bytes(body))
        if common.canonical(doc) != bytes(body) or doc.get("version") != VERSION:
            raise ValueError("S2_RECORD_PROFILE_MISMATCH")
        history = common.audit(conn, job, COMMAND, scope, digest)
        if not history[1][1][2] <= recorded_at <= history[1][2][2]:
            raise ValueError("S2_RECORD_OUTSIDE_AUDIT_INTERVAL")
    return rows


def _insert(target: Any, scope: str, digest: str, body: bytes, job: str) -> None:
    table = common.table(target, TABLE)
    target.execute(f"INSERT INTO {table} VALUES (?,?,?,?,?)", [scope, digest, body, job, datetime.now(UTC)])


def persist(
    bronze: Any,
    target: Any,
    *,
    request: bytes,
    observation_id: str,
    expected_sha256: str,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    common.execution(actor_id, code_revision)
    common.silver_target(target)
    base.separate(bronze, target)
    if not base.pin(observation_id) or not base.pin(expected_sha256):
        raise ValueError("S2_EXACT_OBSERVATION_PINS_REQUIRED")
    rows = _verify(target, observation_id)
    body = observe(bronze, request)
    if base.sha(body) != expected_sha256:
        raise ValueError("S2_REVIEWED_OBSERVATION_CHANGED")
    retry = next((row for row in rows if row[0] == expected_sha256), None)
    if retry is not None:
        if bytes(retry[1]) != body:
            raise ValueError("S2_RETRY_MISMATCH")
    else:
        if len(rows) >= MAX_VARIANTS:
            raise ValueError("S2_VARIANT_BOUND")
        ledger = AuditLedger(target)
        job = ledger.plan_job(
            command_name=COMMAND,
            actor_id=actor_id,
            code_revision=code_revision,
            scope_ref=observation_id,
            config_hash=expected_sha256,
        )
        with ledger.execution(job):
            if observe(bronze, request) != body:
                raise ValueError("S2_SOURCE_DRIFT")
            target.execute("BEGIN TRANSACTION")
            try:
                _insert(target, observation_id, expected_sha256, body, job)
                target.execute("COMMIT")
            except BaseException:
                target.execute("ROLLBACK")
                raise
    final = _verify(target, observation_id)
    if {r[0] for r in final} != {r[0] for r in rows} | {expected_sha256}:
        raise ValueError("S2_FINAL_AUDIT_MISMATCH")
    return dict(
        observation_id=observation_id,
        digest=expected_sha256,
        exact_retry=retry is not None,
        conflicted=len(final) > 1,
        quality_state=json.loads(body)["quality_state"],
        decision_eligibility_asserted=False,
    )


def replay(bronze: Any, reader: Any, *, observation_id: str, expected_sha256: str) -> dict[str, Any]:
    base.readonly(reader)
    base.readonly(bronze)
    base.separate(bronze, reader)
    if not base.pin(observation_id) or not base.pin(expected_sha256):
        raise ValueError("S2_EXACT_OBSERVATION_PINS_REQUIRED")
    rows = _verify(reader, observation_id)
    if len(rows) != 1 or rows[0][0] != expected_sha256:
        raise ValueError("S2_MISSING_CONFLICTED_OR_WRONG_PIN")
    body = bytes(rows[0][1])
    doc = json.loads(body)
    if observe(bronze, common.canonical(doc["request"])) != body:
        raise ValueError("S2_REPLAY_MISMATCH")
    if _verify(reader, observation_id) != rows:
        raise ValueError("S2_FINAL_AUDIT_MISMATCH")
    return doc
