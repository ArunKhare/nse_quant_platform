"""Audited research-window Gold over actual complete persisted candle-return builds."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform import legacy_candle_returns_store as source
from nse_quant.data_platform import legacy_return_windows as features
from nse_quant.data_platform.admission_capture_reader import _lifecycle
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy

VERSION = "legacy-return-window-gold@1"
COMMAND = "build.legacy_return_windows@1"
DOMAIN = (
    "return_window_versions",
    "return_window_builds",
    "return_window_inputs",
    "return_window_outputs",
    "return_window_attempts",
)
TABLES = {("gold", n) for n in DOMAIN} | {
    ("medallion_audit", n) for n in ("schema_versions", "dataset_contracts", "jobs", "job_events")
}
CONTRACT = DatasetContract(
    "gold.legacy_return_windows",
    "1",
    Layer.GOLD,
    WritePolicy.VERSIONED_BUILDS,
    ("build_id", "ordinal"),
    ("build_id", "ordinal", "event_ts", "published_at", "feature_version"),
    "native_legacy_return_windows",
)
MAX_CONTEXT_BYTES = 70000
name = source.name
canonical = source.canonical
sha = source.sha
helpers = source.foundation


@dataclass(frozen=True)
class ReturnWindowPins:
    build_id: str
    recording_fingerprint: str

    def __post_init__(self) -> None:
        if not source.source.codec.pin(self.build_id) or not source.source.codec.pin(
            self.recording_fingerprint
        ):
            raise ValueError("EXACT_WINDOW_RETURN_RECORDING_PINS_REQUIRED")

    def arguments(self) -> dict[str, str]:
        return dict(
            build_id=self.build_id, expected_recording_fingerprint=self.recording_fingerprint
        )


def scope_id(pins: ReturnWindowPins, policy: features.ReturnWindowPolicy) -> str:
    return sha(canonical([VERSION, pins.build_id, asdict(policy)]))


def _definition() -> bytes:
    return canonical(
        [
            VERSION,
            features.VERSION,
            CONTRACT.canonical_json(),
            source._definition().hex(),
            "N adjacent returns from N+1 complete retained observations; explicit elapsed cadence",
            "strictly positive known stable-symbol windows; unavailable never filtered or bridged",
            "exact sum/mean squared simple returns; not log-return RV or annualized volatility",
            features.MAX_ROWS,
            features.MAX_ROW_BYTES,
            features.MAX_TOTAL_BYTES,
            features.MAX_RATIONAL_BITS,
            MAX_CONTEXT_BYTES,
        ]
    )


def _owned(c: Any, *, complete: bool) -> None:
    paths = c.execute(
        "SELECT path FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall()
    if len(paths) != 1 or not paths[0][0]:
        raise ValueError("FILE_BACKED_RETURN_WINDOW_TARGET_REQUIRED")
    rows = c.execute(
        "SELECT table_schema,table_name,table_type FROM information_schema.tables "
        "WHERE table_catalog=current_database() ORDER BY table_schema,table_name LIMIT 10"
    ).fetchall()
    known = {(s, t) for s, t, _ in rows}
    if (
        known - TABLES
        or any(kind != "BASE TABLE" for _, _, kind in rows)
        or complete
        and known != TABLES
    ):
        raise ValueError("DEDICATED_RETURN_WINDOW_TARGET_REQUIRED")


def initialize_return_window_gold(c: Any) -> None:
    _owned(c, complete=False)
    if c.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() LIMIT 1"
    ).fetchone():
        raise ValueError("EMPTY_RETURN_WINDOW_TARGET_REQUIRED")
    AuditLedger(c).initialize()
    versions, builds, inputs, outputs, attempts = (name(c, "gold", n) for n in DOMAIN)
    c.execute("BEGIN TRANSACTION")
    try:
        c.execute(f"CREATE SCHEMA {versions.rsplit('.', 1)[0]}")
        c.execute(f"CREATE TABLE {versions} (version INTEGER PRIMARY KEY,definition BLOB)")
        c.execute(f"INSERT INTO {versions} VALUES (1,?)", [_definition()])
        c.execute(f"""CREATE TABLE {builds} (
            build_id VARCHAR PRIMARY KEY,scope_id VARCHAR UNIQUE NOT NULL,pins BLOB NOT NULL,
            policy BLOB NOT NULL,context BLOB NOT NULL,row_count INTEGER NOT NULL,
            first_job_id VARCHAR NOT NULL,recorded_at TIMESTAMPTZ NOT NULL)""")
        c.execute(f"""CREATE TABLE {inputs} (
            build_id VARCHAR NOT NULL,scope_id VARCHAR NOT NULL,ordinal INTEGER NOT NULL,
            record_id VARCHAR NOT NULL,record_bytes BLOB NOT NULL,PRIMARY KEY(build_id,ordinal))""")
        c.execute(f"""CREATE TABLE {outputs} (
            build_id VARCHAR NOT NULL,scope_id VARCHAR NOT NULL,ordinal INTEGER NOT NULL,
            record_id VARCHAR NOT NULL,event_ts TIMESTAMPTZ NOT NULL,published_at TIMESTAMPTZ,
            feature_version VARCHAR NOT NULL,record_bytes BLOB NOT NULL,
            PRIMARY KEY(build_id,ordinal))""")
        c.execute(
            f"CREATE TABLE {attempts} (job_id VARCHAR PRIMARY KEY,"
            "scope_id VARCHAR NOT NULL,build_id VARCHAR NOT NULL)"
        )
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK")
        raise
    AuditLedger(c).register_contract(CONTRACT)


def _schema(c: Any) -> None:
    _owned(c, complete=True)
    if c.execute(
        f"SELECT version,CASE WHEN octet_length(definition)<=32768 THEN definition END "
        f"FROM {name(c, 'gold', DOMAIN[0])} LIMIT 2"
    ).fetchall() != [(1, _definition())]:
        raise ValueError("RETURN_WINDOW_DEFINITION_DRIFT")
    if c.execute(
        f"SELECT fingerprint,CASE WHEN octet_length(encode(contract_json))<=32768 "
        f"THEN contract_json END FROM {name(c, 'medallion_audit', 'dataset_contracts')} "
        "WHERE dataset_name=? AND contract_version='1'",
        [CONTRACT.name],
    ).fetchall() != [(CONTRACT.fingerprint, CONTRACT.canonical_json())]:
        raise ValueError("RETURN_WINDOW_CONTRACT_DRIFT")
    if c.execute(
        f"SELECT version FROM {name(c, 'medallion_audit', 'schema_versions')} LIMIT 2"
    ).fetchall() != [(1,)]:
        raise ValueError("RETURN_WINDOW_AUDIT_SCHEMA_DRIFT")


def _observe(
    bronze: Any, silver: Any, geometry: Any, returns: Any, pins: ReturnWindowPins
) -> tuple[bytes, tuple[bytes, ...]]:
    first = source.revalidate_candle_return_gold(
        bronze, silver, geometry, returns, **pins.arguments()
    )
    fingerprint, rows, inputs, geometry_pins = source._recording(returns, pins.build_id)
    context_row = returns.execute(
        f"SELECT CASE WHEN octet_length(context)<=32768 THEN context END "
        f"FROM {name(returns, 'gold', source.DOMAIN[1])} WHERE build_id=?",
        [pins.build_id],
    ).fetchone()
    if (
        fingerprint != pins.recording_fingerprint
        or first != rows
        or context_row is None
        or context_row[0] is None
    ):
        raise ValueError("RETURN_WINDOW_NATIVE_SOURCE_RECORDING_DRIFT")
    context = canonical(
        dict(geometry_pins=asdict(geometry_pins), return_context=bytes(context_row[0]).hex())
    )
    if len(context) > MAX_CONTEXT_BYTES:
        raise ValueError("RETURN_WINDOW_CONTEXT_BYTE_BOUND")
    return context, inputs


def _recompute(
    context: bytes,
    inputs: tuple[bytes, ...],
    pins: ReturnWindowPins,
    policy: features.ReturnWindowPolicy,
) -> tuple[bytes, ...]:
    if type(context) is not bytes or not 0 < len(context) <= MAX_CONTEXT_BYTES:
        raise ValueError("RETURN_WINDOW_CONTEXT_BYTE_BOUND")
    value = json.loads(context)
    gp = source.CandleReturnPins(**value["geometry_pins"])
    raw = value["return_context"]
    if type(raw) is not str or len(raw) > 65536:
        raise ValueError("RETURN_WINDOW_NESTED_CONTEXT_BOUND")
    nested = bytes.fromhex(raw)
    if canonical(dict(geometry_pins=asdict(gp), return_context=nested.hex())) != context:
        raise ValueError("RETURN_WINDOW_EXACT_CONTEXT_REQUIRED")
    rows = source._recompute(nested, inputs, gp)
    if source._id(gp, nested, rows) != pins.build_id:
        raise ValueError("RETURN_WINDOW_COMPLETE_RETURN_BUILD_MISMATCH")
    return features.derive_window_records(
        inputs,
        rows,
        source_build_id=pins.build_id,
        source_recording_fingerprint=pins.recording_fingerprint,
        policy=policy,
    )


def _config(pins: ReturnWindowPins, policy: features.ReturnWindowPolicy) -> str:
    return sha(canonical([_definition().hex(), asdict(pins), asdict(policy)]))


def _id(
    pins: ReturnWindowPins,
    policy: features.ReturnWindowPolicy,
    context: bytes,
    rows: tuple[bytes, ...],
) -> str:
    return sha(canonical([_config(pins, policy), context.hex(), [sha(r) for r in rows]]))


def persist_return_window_gold(
    bronze: Any,
    silver: Any,
    geometry: Any,
    returns: Any,
    target: Any,
    *,
    pins: ReturnWindowPins,
    policy: features.ReturnWindowPolicy,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    if type(pins) is not ReturnWindowPins or type(policy) is not features.ReturnWindowPolicy:
        raise TypeError("TYPED_RETURN_WINDOW_PINS_AND_POLICY_REQUIRED")
    pins = ReturnWindowPins(**asdict(pins))
    policy = features.ReturnWindowPolicy(**asdict(policy))
    if (
        not helpers._identifier(actor_id)
        or type(code_revision) is not str
        or re.fullmatch(r"[a-f0-9]{40}", code_revision) is None
    ):
        raise ValueError("EXPLICIT_RETURN_WINDOW_EXECUTION_IDENTIFIERS_REQUIRED")
    for c in (bronze, silver, geometry, returns):
        source.source.foundation._separate(c, target)
    _schema(target)
    scope = scope_id(pins, policy)
    for n in DOMAIN[1:]:
        if target.execute(
            f"SELECT 1 FROM {name(target, 'gold', n)} WHERE scope_id=? LIMIT 1", [scope]
        ).fetchone():
            raise ValueError("RETURN_WINDOW_FIRST_WRITE_OR_ORPHAN_OBLIGATION")
    if target.execute(
        f"SELECT 1 FROM {name(target, 'medallion_audit', 'jobs')} WHERE scope_ref=? LIMIT 1",
        ["sha256:" + scope],
    ).fetchone():
        raise ValueError("RETURN_WINDOW_FIRST_WRITE_ORIGINAL_AUDIT_OBLIGATION")
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref="sha256:" + scope,
        config_hash=_config(pins, policy),
    )
    with ledger.execution(job):
        context, inputs = _observe(bronze, silver, geometry, returns, pins)
        rows = _recompute(context, inputs, pins, policy)
        if _observe(bronze, silver, geometry, returns, pins) != (context, inputs):
            raise ValueError("RETURN_WINDOW_COMPLETE_NATIVE_SOURCE_DRIFT")
        key = _id(pins, policy, context, rows)
        at = datetime.now(UTC)
        target.execute("BEGIN TRANSACTION")
        try:
            target.execute(
                f"INSERT INTO {name(target, 'gold', DOMAIN[1])} VALUES (?,?,?,?,?,?,?,?)",
                [
                    key,
                    scope,
                    canonical(asdict(pins)),
                    canonical(asdict(policy)),
                    context,
                    len(rows),
                    job,
                    at,
                ],
            )
            for ordinal, (raw, row) in enumerate(zip(inputs, rows, strict=True)):
                target.execute(
                    f"INSERT INTO {name(target, 'gold', DOMAIN[2])} VALUES (?,?,?,?,?)",
                    [key, scope, ordinal, sha(raw), raw],
                )
                target.execute(
                    f"INSERT INTO {name(target, 'gold', DOMAIN[3])} VALUES (?,?,?,?,?,?,?,?)",
                    [
                        key,
                        scope,
                        ordinal,
                        sha(row),
                        datetime.fromisoformat(json.loads(row)["event_ts"]),
                        None,
                        features.VERSION,
                        row,
                    ],
                )
            target.execute(
                f"INSERT INTO {name(target, 'gold', DOMAIN[4])} VALUES (?,?,?)", [job, scope, key]
            )
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise
    fingerprint, _rows, _inputs, _pins, _policy = _recording(target, key)
    return dict(
        build_id=key,
        recording_fingerprint=fingerprint,
        row_count=len(rows),
        job_id=job,
        decision_eligibility_asserted=False,
        published=False,
    )


def _recording(
    c: Any, key: str
) -> tuple[
    str, tuple[bytes, ...], tuple[bytes, ...], ReturnWindowPins, features.ReturnWindowPolicy
]:
    if not source.source.codec.pin(key):
        raise ValueError("EXACT_RETURN_WINDOW_BUILD_REQUIRED")
    c.execute("BEGIN TRANSACTION")
    try:
        _schema(c)
        text = helpers._text
        head = c.execute(
            f"SELECT {text('scope_id', 64)},CASE WHEN octet_length(pins)<=512 THEN pins END,"
            "CASE WHEN octet_length(policy)<=512 THEN policy END,"
            f"CASE WHEN octet_length(context)<=? THEN context END,row_count,"
            f"{text('first_job_id')},recorded_at "
            f"FROM {name(c, 'gold', DOMAIN[1])} WHERE build_id=?",
            [MAX_CONTEXT_BYTES, key],
        ).fetchone()
        if head is None or any(head[i] is None for i in (0, 1, 2, 3, 5)):
            raise ValueError("RETURN_WINDOW_BUILD_MISSING_OR_UNBOUNDED")
        groups: list[list[Any]] = []
        for table, per_row, total in (
            (
                DOMAIN[2],
                source.source.codec.MAX_INPUT_ROW_BYTES,
                source.source.codec.MAX_INPUT_TOTAL_BYTES,
            ),
            (DOMAIN[3], features.MAX_ROW_BYTES, features.MAX_TOTAL_BYTES),
        ):
            qualified = name(c, "gold", table)
            budget = c.execute(
                f"SELECT count(*),coalesce(sum(octet_length(record_bytes)),0) FROM {qualified} "
                "WHERE build_id=? OR scope_id=?",
                [key, head[0]],
            ).fetchone()
            if budget is None or not 1 <= budget[0] <= features.MAX_ROWS or budget[1] > total:
                raise ValueError("RETURN_WINDOW_COVERAGE_OR_AGGREGATE_BYTE_BOUND")
            columns = (
                f"{text('build_id', 64)},{text('scope_id', 64)},ordinal,{text('record_id', 64)},"
            )
            if table == DOMAIN[3]:
                columns += f"event_ts,published_at,{text('feature_version')},"
            rows = c.execute(
                f"SELECT {columns}CASE WHEN octet_length(record_bytes)<=? THEN record_bytes END "
                f"FROM {qualified} WHERE build_id=? OR scope_id=? ORDER BY ordinal LIMIT ?",
                [per_row, key, head[0], features.MAX_ROWS + 1],
            ).fetchall()
            groups.append(rows)
        links = c.execute(
            f"SELECT {text('job_id')},{text('scope_id', 64)},{text('build_id', 64)} "
            f"FROM {name(c, 'gold', DOMAIN[4])} "
            "WHERE scope_id=? OR build_id=? OR job_id=? LIMIT 3",
            [head[0], key, head[5]],
        ).fetchall()
        jobs = c.execute(
            f"SELECT {text('job_id')},{text('parent_job_id')},{text('command_name')},"
            f"{text('actor_id')},{text('scope_ref', 71)},{text('code_revision', 40)},"
            f"{text('config_hash', 64)},created_at FROM {name(c, 'medallion_audit', 'jobs')} "
            "WHERE scope_ref=? OR job_id=? LIMIT 3",
            ["sha256:" + head[0], head[5]],
        ).fetchall()
        history = c.execute(
            "SELECT event_index,CASE WHEN length(state)<=32 THEN state END,recorded_at,"
            "CASE WHEN reason_code IS NULL OR octet_length(encode(reason_code))<=64 "
            "THEN reason_code ELSE 'INVALID!' END "
            f"FROM {name(c, 'medallion_audit', 'job_events')} "
            "WHERE job_id=? ORDER BY event_index LIMIT 4",
            [head[5]],
        ).fetchall()
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK")
        raise
    pins = ReturnWindowPins(**json.loads(bytes(head[1])))
    policy = features.ReturnWindowPolicy(**json.loads(bytes(head[2])))
    scope = scope_id(pins, policy)
    retained, stored = groups
    if any(r[-1] is None for r in retained + stored):
        raise ValueError("RETURN_WINDOW_PER_ROW_BYTE_BOUND")
    inputs = tuple(bytes(r[-1]) for r in retained)
    context = bytes(head[3])
    expected = _recompute(context, inputs, pins, policy)
    if (
        head[0] != scope
        or head[4] != len(expected)
        or len(stored) != len(expected)
        or bytes(head[1]) != canonical(asdict(pins))
        or bytes(head[2]) != canonical(asdict(policy))
        or _id(pins, policy, context, expected) != key
        or links != [(head[5], scope, key)]
    ):
        raise ValueError("RETURN_WINDOW_COMPLETE_COVERAGE_MISMATCH")
    for i, (raw, row, actual_input, actual) in enumerate(
        zip(inputs, expected, retained, stored, strict=True)
    ):
        if actual_input != (key, scope, i, sha(raw), raw) or actual != (
            key,
            scope,
            i,
            sha(row),
            datetime.fromisoformat(json.loads(row)["event_ts"]),
            None,
            features.VERSION,
            row,
        ):
            raise ValueError("RETURN_WINDOW_FULL_ROW_RECOMPUTATION_MISMATCH")
    if len(jobs) != 1:
        raise ValueError("RETURN_WINDOW_ORIGINAL_SCOPED_JOB_OBLIGATION")
    job = jobs[0]
    if (
        job[:3] != (head[5], None, COMMAND)
        or not helpers._identifier(job[3])
        or job[4] != "sha256:" + scope
        or type(job[5]) is not str
        or re.fullmatch(r"[a-f0-9]{40}", job[5]) is None
        or job[6] != _config(pins, policy)
        or _lifecycle(history) != "SUCCEEDED"
    ):
        raise ValueError("RETURN_WINDOW_ORIGINAL_AUDIT_NOT_VERIFIED")
    helpers._instant(head[6])
    helpers._instant(job[7])
    metadata = [head[0], bytes(head[1]).hex(), bytes(head[2]).hex(), context.hex(), *head[4:]]
    fingerprint = helpers._hash(
        [
            VERSION,
            key,
            metadata,
            [sha(r) for r in inputs],
            [sha(r) for r in expected],
            links,
            jobs,
            history,
        ]
    )
    return fingerprint, expected, inputs, pins, policy


def read_return_window_gold(
    c: Any, *, build_id: str, expected_recording_fingerprint: str
) -> tuple[bytes, ...]:
    if not source.source.codec.pin(expected_recording_fingerprint):
        raise ValueError("EXACT_RETURN_WINDOW_RECORDING_PIN_REQUIRED")
    if c.execute(
        "SELECT readonly FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall() != [(True,)]:
        raise ValueError("READONLY_RETURN_WINDOW_SOURCE_REQUIRED")
    fingerprint, rows, _inputs, _pins, _policy = _recording(c, build_id)
    if fingerprint != expected_recording_fingerprint:
        raise ValueError("RETURN_WINDOW_RECORDING_FINGERPRINT_CHANGED")
    return rows


def revalidate_return_window_gold(
    bronze: Any,
    silver: Any,
    geometry: Any,
    returns: Any,
    target: Any,
    *,
    build_id: str,
    expected_recording_fingerprint: str,
) -> tuple[bytes, ...]:
    for c in (bronze, silver, geometry, returns):
        source.source.foundation._separate(c, target)
    args = dict(build_id=build_id, expected_recording_fingerprint=expected_recording_fingerprint)
    first = read_return_window_gold(target, **args)
    _fp, _rows, retained, pins, policy = _recording(target, build_id)
    context, inputs = _observe(bronze, silver, geometry, returns, pins)
    if inputs != retained or _recompute(context, inputs, pins, policy) != first:
        raise ValueError("RETURN_WINDOW_CURRENT_NATIVE_SOURCE_CHANGED")
    if read_return_window_gold(target, **args) != first:
        raise ValueError("RETURN_WINDOW_CHANGED_DURING_REVALIDATION")
    return first
