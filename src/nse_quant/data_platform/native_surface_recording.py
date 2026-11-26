"""Audited, offline S2 surface recording over reviewed native Bronze snapshots."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from nse_quant.data_platform import india_vix_recording as common
from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform import surface_evidence_bundle as bundle
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.native_option_chain_snapshot_bronze import read_option_chain_snapshot_bronze

VERSION = "native-s2-surface-recording@1"
COMMAND = "persist.native_s2_surface@1"
TABLE = "silver.s2_surface_variants"
MAX_ARTIFACT = 65536
MAX_RECORD = 10 * 1024 * 1024
IST = ZoneInfo("Asia/Kolkata")
PIN_FIELDS = {"source_label", "snapshot_id", "capture_event_id", "envelope_hash", "expected_recording_fingerprint"}


def _object(raw: bytes) -> dict[str, Any]:
    doc = json.loads(raw)
    if not isinstance(doc, dict) or common.canonical(doc) != raw:
        raise ValueError("CANONICAL_OBJECT_REQUIRED")
    return doc


def _clock(text: str) -> datetime:
    dt = datetime.fromisoformat(text)
    if dt.utcoffset() is None:
        raise ValueError("AWARE_CLOCK_REQUIRED")
    return dt.astimezone(UTC)


def _artifact(raw: bytes, pin: str, kind: str) -> Any:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_ARTIFACT or bundle.sha256(raw) != pin:
        raise ValueError("ARTIFACT_PIN_OR_BOUND_MISMATCH")
    doc = _object(raw)
    if set(doc) != {"kind", "data"} or doc["kind"] != kind:
        raise ValueError("ARTIFACT_KIND_MISMATCH")
    return doc["data"]


def assemble(
    bronze: Any, *, snapshots: list[dict[str, str]], artifacts: dict[str, tuple[bytes, str]], policy: dict[str, Any]
) -> bytes:
    """Project reviewed native records; never use caller-supplied premium rows."""
    base.readonly(bronze)
    if not 1 <= len(snapshots) <= 16 or set(artifacts) != {"calendar", "forward", "rate"}:
        raise ValueError("EXACT_SURFACE_SOURCE_SET_REQUIRED")
    parts = {kind: _artifact(raw, pin, kind) for kind, (raw, pin) in artifacts.items()}
    calendar = parts["calendar"]
    dates = {}
    for text in calendar["closes"]:
        date = _clock(text).astimezone(IST).date().isoformat()
        if date in dates:
            raise ValueError("AMBIGUOUS_EXPIRY_DATE")
        dates[date] = text
    forwards = parts["forward"]
    rates = parts["rate"]
    if set(rates) != {row["expiry_close"] for row in forwards}:
        raise ValueError("FORWARD_RATE_COVERAGE_MISMATCH")
    if any(set(row) != {"expiry_close", "kind", "evidence"} for row in forwards):
        raise ValueError("FORWARD_ARTIFACT_FIELDS_MISMATCH")
    forwards = [dict(row, rate=rates[row["expiry_close"]]) for row in forwards]
    ordered = sorted(snapshots, key=lambda pin: pin["snapshot_id"])
    if len({pin["snapshot_id"] for pin in ordered}) != len(ordered):
        raise ValueError("DUPLICATE_NATIVE_SNAPSHOT")
    batch = bundle.sha256(common.canonical(ordered))
    identity = None
    expiries = set()
    premiums = []
    for pins in ordered:
        if set(pins) != PIN_FIELDS:
            raise ValueError("EXACT_NATIVE_SNAPSHOT_PINS_REQUIRED")
        for raw in read_option_chain_snapshot_bronze(bronze, **pins):
            row = json.loads(raw)["stored_fields"]
            quote = row["quote"]
            inst = quote["instrument"]
            current = (row["underlying"], _clock(row["ts"]))
            if identity is None:
                identity = current
            if (
                identity != current
                or current[1] > _clock(policy["as_of"])
                or row["expiry"] != inst["expiry"]
                or row["underlying"] != inst["underlying"]
            ):
                raise ValueError("NATIVE_SNAPSHOT_COHORT_MISMATCH")
            if row["expiry"] not in dates:
                raise ValueError("NATIVE_EXPIRY_CLOSE_NOT_LINKED")
            source = quote["exchange_ts"] or quote["trade_ts"]
            if source is None or quote["bid"] is None or quote["ask"] is None:
                raise ValueError("NATIVE_QUOTE_CLOCKS_AND_PREMIUM_REQUIRED")
            expiries.add((row["expiry"], pins["snapshot_id"]))
            premiums.append(
                dict(
                    token=inst["instrument_token"],
                    underlying=row["underlying"],
                    batch_id=batch,
                    expiry_close=dates[row["expiry"]],
                    strike=inst["strike"],
                    option_type=inst["option_type"],
                    bid=quote["bid"],
                    ask=quote["ask"],
                    source_time=source,
                    received_at=quote["received_at"],
                )
            )
            if len(premiums) > bundle.MAX_QUOTES:
                raise ValueError("PREMIUM_COUNT_BOUND")
    if len(expiries) != len({expiry for expiry, _ in expiries}):
        raise ValueError("DUPLICATE_NATIVE_EXPIRY_SNAPSHOT")
    evidence = dict(policy=policy, calendar=calendar, forwards=forwards, premiums=premiums)
    raw = common.canonical(
        dict(
            version=VERSION,
            snapshots=ordered,
            artifacts={k: [v.hex(), pin] for k, (v, pin) in artifacts.items()},
            policy=policy,
            bundle=json.loads(bundle.build_bundle(evidence)),
        )
    )
    if len(raw) > MAX_RECORD:
        raise ValueError("RECORD_BYTE_BOUND")
    return raw


def initialize(target: Any, *, actor_id: str, code_revision: str) -> None:
    common.execution(actor_id, code_revision)
    common.silver_target(target)
    AuditLedger(target).initialize()
    target.execute("CREATE SCHEMA IF NOT EXISTS silver")
    table = common.table(target, TABLE)
    target.execute(
        f"CREATE TABLE IF NOT EXISTS {table} (scope VARCHAR, digest VARCHAR, body BLOB NOT NULL, "
        "job_id VARCHAR NOT NULL, PRIMARY KEY(scope,digest))"
    )


def _variants(conn: Any, scope: str) -> list[tuple[Any, ...]]:
    table = common.table(conn, TABLE)
    return conn.execute(
        f"SELECT digest, CASE WHEN octet_length(body)<=? THEN body END, job_id FROM {table} WHERE scope=? LIMIT 2",
        [MAX_RECORD, scope],
    ).fetchall()


def _verified(conn: Any, row: tuple[Any, ...], scope: str) -> bytes:
    digest, body, job = row
    if body is None or bundle.sha256(bytes(body)) != digest:
        raise ValueError("SURFACE_RECORD_INTEGRITY_MISMATCH")
    common.audit(conn, job, COMMAND, scope, digest)
    return bytes(body)


def _inputs(doc: dict[str, Any]) -> dict[str, Any]:
    return dict(
        snapshots=doc["snapshots"],
        policy=doc["policy"],
        artifacts={k: (bytes.fromhex(raw), pin) for k, (raw, pin) in doc["artifacts"].items()},
    )


def persist(
    bronze: Any,
    target: Any,
    *,
    observation_id: str,
    expected_sha256: str,
    actor_id: str,
    code_revision: str,
    snapshots: list[dict[str, str]],
    artifacts: dict[str, tuple[bytes, str]],
    policy: dict[str, Any],
) -> dict[str, Any]:
    """Retain competing valid observations, quarantine the identity, never overwrite."""
    common.execution(actor_id, code_revision)
    common.silver_target(target)
    base.separate(bronze, target)
    if not base.pin(observation_id) or not base.pin(expected_sha256):
        raise ValueError("EXACT_SURFACE_PINS_REQUIRED")
    original = assemble(bronze, snapshots=snapshots, artifacts=artifacts, policy=policy)
    if bundle.sha256(original) != expected_sha256:
        raise ValueError("REVIEWED_SURFACE_CHANGED")
    table = common.table(target, TABLE)
    variant = target.execute(
        f"SELECT digest, CASE WHEN octet_length(body)<=? THEN body END, job_id FROM {table} WHERE scope=? AND digest=?",
        [MAX_RECORD, observation_id, expected_sha256],
    ).fetchone()
    existing = _variants(target, observation_id)
    for row in existing:
        _verified(target, row, observation_id)
    if variant is not None:
        if _verified(target, variant, observation_id) != original:
            raise ValueError("SURFACE_RETRY_MISMATCH")
    else:
        ledger = AuditLedger(target)
        job = ledger.plan_job(
            command_name=COMMAND,
            actor_id=actor_id,
            code_revision=code_revision,
            scope_ref=observation_id,
            config_hash=expected_sha256,
        )
        with ledger.execution(job):
            if assemble(bronze, **_inputs(_object(original))) != original:
                raise ValueError("SURFACE_SOURCE_DRIFT")
            target.execute(f"INSERT INTO {table} VALUES (?,?,?,?)", [observation_id, expected_sha256, original, job])
    return dict(
        conflicted=len(existing) > 1 or (bool(existing) and variant is None),
        exact_retry=variant is not None,
        decision_eligibility_asserted=False,
    )


def replay(bronze: Any, reader: Any, *, observation_id: str, expected_sha256: str) -> dict[str, Any]:
    base.separate(bronze, reader)
    base.readonly(reader)
    if not base.pin(observation_id) or not base.pin(expected_sha256):
        raise ValueError("EXACT_SURFACE_PINS_REQUIRED")
    rows = _variants(reader, observation_id)
    if len(rows) != 1 or rows[0][0] != expected_sha256:
        raise ValueError("SURFACE_MISSING_CONFLICTED_OR_WRONG_PIN")
    raw = _verified(reader, rows[0], observation_id)
    doc = _object(raw)
    if assemble(bronze, **_inputs(doc)) != raw or _variants(reader, observation_id) != rows:
        raise ValueError("SURFACE_REPLAY_MISMATCH")
    return doc["bundle"]["result"]



def read_recording_metadata(
    reader: Any, *, observation_id: str, expected_sha256: str
) -> tuple[dict[str, Any], str]:
    """Read one exact audited surface recording and return its retained document/job pin."""
    base.readonly(reader)
    if not base.pin(observation_id) or not base.pin(expected_sha256):
        raise ValueError("EXACT_SURFACE_PINS_REQUIRED")
    rows = _variants(reader, observation_id)
    if len(rows) != 1 or rows[0][0] != expected_sha256:
        raise ValueError("SURFACE_MISSING_CONFLICTED_OR_WRONG_PIN")
    raw = _verified(reader, rows[0], observation_id)
    return _object(raw), str(rows[0][2])
