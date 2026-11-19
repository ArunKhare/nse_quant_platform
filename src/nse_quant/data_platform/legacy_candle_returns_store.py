"""Audited complete native candle-return builds over actual migrated-price Gold."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform import legacy_candle_returns as features
from nse_quant.data_platform import legacy_market_gold_store as source
from nse_quant.data_platform import legacy_market_publication as foundation
from nse_quant.data_platform.admission_capture_reader import _lifecycle
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy

VERSION = "legacy-candle-return-gold@1"
COMMAND = "build.legacy_candle_returns@1"
DOMAIN = (
    "legacy_return_versions",
    "legacy_return_builds",
    "legacy_return_inputs",
    "legacy_return_outputs",
    "legacy_return_attempts",
)
TABLES = {("gold", n) for n in DOMAIN} | {
    ("medallion_audit", n) for n in ("schema_versions", "dataset_contracts", "jobs", "job_events")
}
CONTRACT = DatasetContract(
    "gold.legacy_candle_returns",
    "1",
    Layer.GOLD,
    WritePolicy.VERSIONED_BUILDS,
    ("build_id", "ordinal"),
    ("build_id", "ordinal", "event_ts", "published_at", "feature_version"),
    "native_legacy_candle_returns",
)
name = source.name
canonical = source.codec.canonical
sha = source.codec.sha


@dataclass(frozen=True)
class CandleReturnPins:
    build_id: str
    recording_fingerprint: str

    def __post_init__(self) -> None:
        if not source.codec.pin(self.build_id) or not source.codec.pin(self.recording_fingerprint):
            raise ValueError("EXACT_CANDLE_RETURN_GOLD_PINS_REQUIRED")

    def arguments(self) -> dict[str, str]:
        return dict(
            build_id=self.build_id, expected_recording_fingerprint=self.recording_fingerprint
        )

    @property
    def scope_id(self) -> str:
        return sha(canonical([VERSION, self.build_id]))


def _definition() -> bytes:
    return canonical(
        [
            VERSION,
            features.VERSION,
            CONTRACT.canonical_json(),
            source._definition().hex(),
            "complete source inputs, one output per source ordinal; no selection or bridging",
            "group retained token/interval, "
            "chronological UTC stored instants; symbol changes flagged",
            "simple=(current-previous)/previous; exact rational stored binary64, "
            "no log/RV/annualization",
            source.codec.MAX_ROWS,
            source.codec.MAX_INPUT_TOTAL_BYTES,
            features.MAX_ROW_BYTES,
            features.MAX_TOTAL_BYTES,
        ]
    )


def _owned(c: Any, *, complete: bool) -> None:
    paths = c.execute(
        "SELECT path FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall()
    if len(paths) != 1 or not paths[0][0]:
        raise ValueError("FILE_BACKED_CANDLE_RETURN_TARGET_REQUIRED")
    rows = c.execute(
        "SELECT table_schema,table_name,table_type FROM information_schema.tables "
        "WHERE table_catalog=current_database() ORDER BY table_schema,table_name LIMIT 10"
    ).fetchall()
    known = {(s, t) for s, t, _ in rows}
    if known - TABLES or any(k != "BASE TABLE" for _, _, k in rows) or complete and known != TABLES:
        raise ValueError("DEDICATED_CANDLE_RETURN_TARGET_REQUIRED")


def initialize_candle_return_gold(c: Any) -> None:
    _owned(c, complete=False)
    if c.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() LIMIT 1"
    ).fetchone():
        raise ValueError("EMPTY_CANDLE_RETURN_TARGET_REQUIRED")
    AuditLedger(c).initialize()
    versions, builds, inputs, outputs, attempts = (name(c, "gold", n) for n in DOMAIN)
    c.execute("BEGIN TRANSACTION")
    try:
        c.execute(f"CREATE SCHEMA {versions.rsplit('.', 1)[0]}")
        c.execute(f"CREATE TABLE {versions} (version INTEGER PRIMARY KEY,definition BLOB)")
        c.execute(f"INSERT INTO {versions} VALUES (1,?)", [_definition()])
        c.execute(f"""CREATE TABLE {builds} (
            build_id VARCHAR PRIMARY KEY,scope_id VARCHAR UNIQUE NOT NULL,
            source_build_id VARCHAR UNIQUE NOT NULL,pins BLOB NOT NULL,context BLOB NOT NULL,
            row_count INTEGER NOT NULL,first_job_id VARCHAR NOT NULL,recorded_at TIMESTAMPTZ)""")
        c.execute(f"""CREATE TABLE {inputs} (
            build_id VARCHAR,source_build_id VARCHAR,ordinal INTEGER,record_id VARCHAR,
            record_bytes BLOB,PRIMARY KEY(build_id,ordinal))""")
        c.execute(f"""CREATE TABLE {outputs} (
            build_id VARCHAR,source_build_id VARCHAR,ordinal INTEGER,record_id VARCHAR,
            event_ts TIMESTAMPTZ,published_at TIMESTAMPTZ,feature_version VARCHAR,
            record_bytes BLOB,PRIMARY KEY(build_id,ordinal))""")
        c.execute(
            f"CREATE TABLE {attempts} (job_id VARCHAR PRIMARY KEY,"
            "scope_id VARCHAR,build_id VARCHAR)"
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
        raise ValueError("CANDLE_RETURN_DEFINITION_DRIFT")
    if c.execute(
        f"SELECT fingerprint,CASE WHEN octet_length(encode(contract_json))<=32768 "
        f"THEN contract_json END FROM {name(c, 'medallion_audit', 'dataset_contracts')} "
        "WHERE dataset_name=? AND contract_version='1'",
        [CONTRACT.name],
    ).fetchall() != [(CONTRACT.fingerprint, CONTRACT.canonical_json())]:
        raise ValueError("CANDLE_RETURN_CONTRACT_DRIFT")
    if c.execute(
        f"SELECT version FROM {name(c, 'medallion_audit', 'schema_versions')} LIMIT 2"
    ).fetchall() != [(1,)]:
        raise ValueError("CANDLE_RETURN_AUDIT_SCHEMA_DRIFT")


def _observe(
    bronze: Any, silver: Any, gold: Any, pins: CandleReturnPins
) -> tuple[bytes, tuple[bytes, ...]]:
    first = source.revalidate_legacy_price_gold(bronze, silver, gold, **pins.arguments())
    fingerprint, outputs, inputs, silver_pins = source._recording(gold, pins.build_id)
    if fingerprint != pins.recording_fingerprint or outputs != first:
        raise ValueError("CANDLE_RETURN_NATIVE_SOURCE_DRIFT")
    context = canonical(dict(silver_pins=asdict(silver_pins), runtime=source._runtime().hex()))
    return context, inputs


def _recompute(
    context: bytes, inputs: tuple[bytes, ...], pins: CandleReturnPins
) -> tuple[bytes, ...]:
    if not 0 < len(context) <= 32768:
        raise ValueError("CANDLE_RETURN_CONTEXT_BYTE_BOUND")
    value = json.loads(context)
    silver_pins = source.codec.GoldSourcePins(**value["silver_pins"])
    if (
        context != canonical(dict(silver_pins=asdict(silver_pins), runtime=value["runtime"]))
        or value["runtime"] != source._runtime().hex()
    ):
        raise ValueError("CANDLE_RETURN_EXACT_CONTEXT_RUNTIME_REQUIRED")
    geometry = source.codec.derive_gold_records(inputs, pins=silver_pins)
    if source._build_id(silver_pins, source._runtime(), inputs, geometry) != pins.build_id:
        raise ValueError("CANDLE_RETURN_COMPLETE_SOURCE_BUILD_MISMATCH")
    return features.derive_return_records(
        inputs,
        source_build_id=pins.build_id,
        source_recording_fingerprint=pins.recording_fingerprint,
    )


def _id(pins: CandleReturnPins, context: bytes, rows: tuple[bytes, ...]) -> str:
    return sha(
        canonical([_definition().hex(), asdict(pins), context.hex(), [sha(r) for r in rows]])
    )


def _config(pins: CandleReturnPins) -> str:
    return sha(canonical([_definition().hex(), asdict(pins)]))


def persist_candle_return_gold(
    bronze: Any,
    silver: Any,
    gold: Any,
    target: Any,
    *,
    pins: CandleReturnPins,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    if type(pins) is not CandleReturnPins:
        raise TypeError("TYPED_CANDLE_RETURN_PINS_REQUIRED")
    pins = CandleReturnPins(**asdict(pins))
    if (
        not foundation._identifier(actor_id)
        or type(code_revision) is not str
        or re.fullmatch(r"[a-f0-9]{40}", code_revision) is None
    ):
        raise ValueError("EXPLICIT_CANDLE_RETURN_EXECUTION_IDENTIFIERS_REQUIRED")
    for conn in (bronze, silver, gold):
        source.foundation._separate(conn, target)
    _schema(target)
    for n in DOMAIN[1:]:
        column = "scope_id" if n == DOMAIN[4] else "source_build_id"
        value = pins.scope_id if column == "scope_id" else pins.build_id
        if target.execute(
            f"SELECT 1 FROM {name(target, 'gold', n)} WHERE {column}=? LIMIT 1", [value]
        ).fetchone():
            raise ValueError("CANDLE_RETURN_FIRST_WRITE_OR_ORPHAN_OBLIGATION")
    if target.execute(
        f"SELECT 1 FROM {name(target, 'medallion_audit', 'jobs')} WHERE scope_ref=? LIMIT 1",
        ["sha256:" + pins.scope_id],
    ).fetchone():
        raise ValueError("CANDLE_RETURN_FIRST_WRITE_ORIGINAL_AUDIT_OBLIGATION")
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref="sha256:" + pins.scope_id,
        config_hash=_config(pins),
    )
    with ledger.execution(job):
        context, inputs = _observe(bronze, silver, gold, pins)
        rows = _recompute(context, inputs, pins)
        if _observe(bronze, silver, gold, pins) != (context, inputs):
            raise ValueError("CANDLE_RETURN_COMPLETE_SOURCE_DRIFT")
        key = _id(pins, context, rows)
        at = datetime.now(UTC)
        target.execute("BEGIN TRANSACTION")
        try:
            target.execute(
                f"INSERT INTO {name(target, 'gold', DOMAIN[1])} VALUES (?,?,?,?,?,?,?,?)",
                [
                    key,
                    pins.scope_id,
                    pins.build_id,
                    canonical(asdict(pins)),
                    context,
                    len(rows),
                    job,
                    at,
                ],
            )
            for ordinal, (raw, row) in enumerate(zip(inputs, rows, strict=True)):
                target.execute(
                    f"INSERT INTO {name(target, 'gold', DOMAIN[2])} VALUES (?,?,?,?,?)",
                    [key, pins.build_id, ordinal, sha(raw), raw],
                )
                ts = datetime.fromisoformat(json.loads(row)["event_ts"])
                target.execute(
                    f"INSERT INTO {name(target, 'gold', DOMAIN[3])} VALUES (?,?,?,?,?,?,?,?)",
                    [key, pins.build_id, ordinal, sha(row), ts, None, features.VERSION, row],
                )
            target.execute(
                f"INSERT INTO {name(target, 'gold', DOMAIN[4])} VALUES (?,?,?)",
                [job, pins.scope_id, key],
            )
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise
    fingerprint, _rows, _inputs, _pins = _recording(target, key)
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
) -> tuple[str, tuple[bytes, ...], tuple[bytes, ...], CandleReturnPins]:
    if not source.codec.pin(key):
        raise ValueError("EXACT_CANDLE_RETURN_BUILD_REQUIRED")
    c.execute("BEGIN TRANSACTION")
    try:
        _schema(c)
        text = foundation._text
        head = c.execute(
            f"SELECT {text('scope_id', 64)},{text('source_build_id', 64)},"
            "CASE WHEN octet_length(pins)<=512 THEN pins END,"
            "CASE WHEN octet_length(context)<=32768 THEN context END,"
            f"row_count,{text('first_job_id')},recorded_at "
            f"FROM {name(c, 'gold', DOMAIN[1])} WHERE build_id=?",
            [key],
        ).fetchone()
        if head is None or any(head[i] is None for i in (0, 1, 2, 3, 5)):
            raise ValueError("CANDLE_RETURN_BUILD_MISSING_OR_UNBOUNDED")
        groups: list[list[Any]] = []
        for table, per_row, total in (
            (DOMAIN[2], source.codec.MAX_INPUT_ROW_BYTES, source.codec.MAX_INPUT_TOTAL_BYTES),
            (DOMAIN[3], features.MAX_ROW_BYTES, features.MAX_TOTAL_BYTES),
        ):
            qualified = name(c, "gold", table)
            budget = c.execute(
                f"SELECT count(*),coalesce(sum(octet_length(record_bytes)),0) FROM {qualified} "
                "WHERE build_id=? OR source_build_id=?",
                [key, head[1]],
            ).fetchone()
            if budget is None or not 1 <= budget[0] <= features.MAX_ROWS or budget[1] > total:
                raise ValueError("CANDLE_RETURN_COVERAGE_OR_AGGREGATE_BYTE_BOUND")
            prefix = (
                f"{text('build_id', 64)},{text('source_build_id', 64)},ordinal,"
                f"{text('record_id', 64)},"
            )
            if table == DOMAIN[3]:
                prefix += f"event_ts,published_at,{text('feature_version')},"
            rows = c.execute(
                f"SELECT {prefix}CASE WHEN octet_length(record_bytes)<=? THEN record_bytes END "
                f"FROM {qualified} WHERE build_id=? OR source_build_id=? ORDER BY ordinal LIMIT ?",
                [per_row, key, head[1], features.MAX_ROWS + 1],
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
    pins = CandleReturnPins(**json.loads(bytes(head[2])))
    retained, stored = groups
    if any(r[-1] is None for r in retained + stored):
        raise ValueError("CANDLE_RETURN_PER_ROW_BYTE_BOUND")
    inputs = tuple(bytes(r[-1]) for r in retained)
    context = bytes(head[3])
    expected = _recompute(context, inputs, pins)
    if (
        head[:2] != (pins.scope_id, pins.build_id)
        or head[4] != len(expected)
        or bytes(head[2]) != canonical(asdict(pins))
        or _id(pins, context, expected) != key
        or len(stored) != len(expected)
        or links != [(head[5], pins.scope_id, key)]
    ):
        raise ValueError("CANDLE_RETURN_COMPLETE_COVERAGE_MISMATCH")
    for i, (raw, row, got_input, got) in enumerate(
        zip(inputs, expected, retained, stored, strict=True)
    ):
        if got_input != (key, pins.build_id, i, sha(raw), raw) or got != (
            key,
            pins.build_id,
            i,
            sha(row),
            datetime.fromisoformat(json.loads(row)["event_ts"]),
            None,
            features.VERSION,
            row,
        ):
            raise ValueError("CANDLE_RETURN_FULL_ROW_RECOMPUTATION_MISMATCH")
    if len(jobs) != 1:
        raise ValueError("CANDLE_RETURN_ORIGINAL_SCOPED_JOB_OBLIGATION")
    job = jobs[0]
    if (
        job[:3] != (head[5], None, COMMAND)
        or not foundation._identifier(job[3])
        or job[4] != "sha256:" + pins.scope_id
        or type(job[5]) is not str
        or re.fullmatch(r"[a-f0-9]{40}", job[5]) is None
        or job[6] != _config(pins)
        or _lifecycle(history) != "SUCCEEDED"
    ):
        raise ValueError("CANDLE_RETURN_ORIGINAL_AUDIT_NOT_VERIFIED")
    foundation._instant(head[6])
    foundation._instant(job[7])
    metadata = [*head[:2], bytes(head[2]).hex(), context.hex(), *head[4:]]
    fingerprint = foundation._hash(
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
    return fingerprint, expected, inputs, pins


def read_candle_return_gold(
    c: Any, *, build_id: str, expected_recording_fingerprint: str
) -> tuple[bytes, ...]:
    if not source.codec.pin(expected_recording_fingerprint):
        raise ValueError("EXACT_CANDLE_RETURN_RECORDING_PIN_REQUIRED")
    if c.execute(
        "SELECT readonly FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall() != [(True,)]:
        raise ValueError("READONLY_CANDLE_RETURN_SOURCE_REQUIRED")
    fingerprint, rows, _inputs, _pins = _recording(c, build_id)
    if fingerprint != expected_recording_fingerprint:
        raise ValueError("CANDLE_RETURN_RECORDING_FINGERPRINT_CHANGED")
    return rows


def revalidate_candle_return_gold(
    bronze: Any,
    silver: Any,
    gold: Any,
    target: Any,
    *,
    build_id: str,
    expected_recording_fingerprint: str,
) -> tuple[bytes, ...]:
    for conn in (bronze, silver, gold):
        source.foundation._separate(conn, target)
    args = dict(build_id=build_id, expected_recording_fingerprint=expected_recording_fingerprint)
    first = read_candle_return_gold(target, **args)
    _fingerprint, _rows, retained, pins = _recording(target, build_id)
    context, fresh = _observe(bronze, silver, gold, pins)
    if fresh != retained or _recompute(context, fresh, pins) != first:
        raise ValueError("CANDLE_RETURN_CURRENT_NATIVE_SOURCE_CHANGED")
    if read_candle_return_gold(target, **args) != first:
        raise ValueError("CANDLE_RETURN_CHANGED_DURING_REVALIDATION")
    return first
