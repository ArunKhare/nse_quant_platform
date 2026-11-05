"""Persisted source-linked retained gate-results Silver; never native approval."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform import legacy_gate_results as codec
from nse_quant.data_platform import legacy_gate_results_bronze as source
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy

VERSION = "legacy-gate-results-silver-recording@1"
COMMAND = "normalize.legacy_gate_results@1"
MAX_CONTEXT = 2200000
MAX_RECORD = codec.MAX_RECORD
MAX_RECORDS = codec.MAX_RECORDS
MAX_SCALAR_BYTES = codec.MAX_BYTES
SCHEMA = codec.SCHEMA
CONTRACT = DatasetContract(
    "silver.legacy_gate_results_observations",
    "1",
    Layer.SILVER,
    WritePolicy.APPEND_REVISIONS,
    ("revision_id", "ordinal"),
    ("revision_id", "ordinal", "recorded_at", "source_observation_id", "record_bytes"),
    "native_legacy_gate_results_silver",
)
DEFINITION = (
    VERSION,
    COMMAND,
    codec.DEFINITION,
    source.DEFINITION,
    CONTRACT.canonical_json(),
    SCHEMA,
    MAX_CONTEXT,
    MAX_RECORD,
    MAX_RECORDS,
    MAX_SCALAR_BYTES,
    "complete snapshot and every source ordinal; exact nine nullable retained scalars",
    "stored TIMESTAMPTZ remains an aware instant or unknown; never a naive wall tuple",
    "passed is retained nullable boolean; reason/details remain opaque text",
    "only gate_result_id is retained key; no natural run/proposal/strategy/gate/time key",
    "first write per native capture event; review pins cannot heal an original obligation",
)
DOMAIN = (
    "gate_results_versions",
    "gate_results_sets",
    "gate_results_observations",
    "gate_results_attempts",
)
TABLES = {("silver", n) for n in DOMAIN} | {
    ("medallion_audit", n) for n in ("schema_versions", "dataset_contracts", "jobs", "job_events")
}
common = source.common


@dataclass(frozen=True)
class GateResultsBronzePins:
    source_label: str
    snapshot_id: str
    capture_event_id: str
    envelope_hash: str
    recording_fingerprint: str

    def __post_init__(self) -> None:
        if not codec.label(self.source_label) or not all(
            codec.pin(p)
            for p in (
                self.snapshot_id,
                self.capture_event_id,
                self.envelope_hash,
                self.recording_fingerprint,
            )
        ):
            raise codec.Rejected("EXACT_GATE_RESULTS_BRONZE_PINS_REQUIRED")

    @property
    def scope_id(self) -> str:
        return codec.sha(codec.canonical([VERSION, self.capture_event_id]))

    def reader_args(self) -> dict[str, str]:
        return dict(
            source_label=self.source_label,
            snapshot_id=self.snapshot_id,
            capture_event_id=self.capture_event_id,
            envelope_hash=self.envelope_hash,
            expected_recording_fingerprint=self.recording_fingerprint,
        )


def _pins(value: GateResultsBronzePins) -> GateResultsBronzePins:
    if type(value) is not GateResultsBronzePins:
        raise codec.Rejected("TYPED_GATE_RESULTS_BRONZE_PINS_REQUIRED")
    return GateResultsBronzePins(**asdict(value))


def _owned(c: Any, *, complete: bool) -> None:
    paths = c.execute(
        "SELECT path FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall()
    if len(paths) != 1 or not paths[0][0]:
        raise codec.Rejected("FILE_BACKED_GATE_RESULTS_SILVER_REQUIRED")
    rows = c.execute(
        "SELECT CASE WHEN octet_length(encode(table_schema))<=128 THEN table_schema END,"
        "CASE WHEN octet_length(encode(table_name))<=128 THEN table_name END,table_type "
        "FROM information_schema.tables WHERE table_catalog=current_database() LIMIT 9"
    ).fetchall()
    known = {(s, t) for s, t, _ in rows}
    if (
        known - TABLES
        or any(kind != "BASE TABLE" for _, _, kind in rows)
        or complete
        and known != TABLES
    ):
        raise codec.Rejected("DEDICATED_GATE_RESULTS_SILVER_REQUIRED")


def _dependency() -> None:
    if (
        tuple(codec.SCHEMA) != SCHEMA
        or codec.VERSION != "legacy-gate-results-snapshot@1"
        or source.VERSION != "legacy-gate-results-bronze-recording@1"
    ):
        raise codec.Rejected("UNSUPPORTED_GATE_RESULTS_SILVER_DEPENDENCY")


def initialize_gate_results_silver(c: Any) -> None:
    """Explicit empty dedicated file target; partial initialization is never adopted."""
    _dependency()
    _owned(c, complete=False)
    if c.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() LIMIT 1"
    ).fetchone():
        raise codec.Rejected("EMPTY_GATE_RESULTS_SILVER_INITIALIZATION_REQUIRED")
    AuditLedger(c).initialize()
    versions, sets, observations, attempts = (common.name(c, "silver", n) for n in DOMAIN)
    scalars = ",".join(
        f'"{n}" {kind}{" NOT NULL" if n == "gate_result_id" else ""}' for n, kind in SCHEMA
    )
    c.execute("BEGIN TRANSACTION")
    try:
        c.execute(f"CREATE SCHEMA {versions.rsplit('.', 1)[0]}")
        c.execute(f"CREATE TABLE {versions} (version INTEGER PRIMARY KEY,definition BLOB NOT NULL)")
        c.execute(f"INSERT INTO {versions} VALUES (1,?)", [codec.canonical(DEFINITION)])
        c.execute(
            f"CREATE TABLE {sets} (revision_id VARCHAR PRIMARY KEY,"
            "scope_id VARCHAR UNIQUE NOT NULL,context BLOB NOT NULL,"
            "row_count INTEGER NOT NULL,first_job_id VARCHAR NOT NULL,"
            "recorded_at TIMESTAMPTZ NOT NULL)"
        )
        c.execute(
            f"CREATE TABLE {observations} (revision_id VARCHAR NOT NULL,"
            "ordinal INTEGER NOT NULL,record_id VARCHAR NOT NULL,"
            f"{scalars},record_bytes BLOB NOT NULL,"
            "source_observation_id VARCHAR NOT NULL,recorded_at TIMESTAMPTZ NOT NULL,"
            "PRIMARY KEY(revision_id,ordinal),UNIQUE(revision_id,gate_result_id))"
        )
        c.execute(
            f"CREATE TABLE {attempts} (job_id VARCHAR PRIMARY KEY,"
            "scope_id VARCHAR NOT NULL,revision_id VARCHAR NOT NULL)"
        )
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK")
        raise
    AuditLedger(c).register_contract(CONTRACT)


def _schema(c: Any) -> None:
    _dependency()
    _owned(c, complete=True)
    if c.execute(
        f"SELECT version,CASE WHEN octet_length(definition)<=32768 THEN definition END "
        f"FROM {common.name(c, 'silver', DOMAIN[0])} LIMIT 2"
    ).fetchall() != [(1, codec.canonical(DEFINITION))]:
        raise codec.Rejected("GATE_RESULTS_SILVER_DEFINITION_DRIFT")
    if c.execute(
        "SELECT CASE WHEN length(fingerprint)<=64 THEN fingerprint END,"
        "CASE WHEN octet_length(encode(contract_json))<=32768 THEN contract_json END "
        f"FROM {common.name(c, 'medallion_audit', 'dataset_contracts')} "
        "WHERE dataset_name=? AND contract_version='1'",
        [CONTRACT.name],
    ).fetchall() != [(CONTRACT.fingerprint, CONTRACT.canonical_json())]:
        raise codec.Rejected("GATE_RESULTS_SILVER_CONTRACT_DRIFT")
    if c.execute(
        f"SELECT version FROM {common.name(c, 'medallion_audit', 'schema_versions')} LIMIT 2"
    ).fetchall() != [(1,)]:
        raise codec.Rejected("GATE_RESULTS_SILVER_AUDIT_SCHEMA_DRIFT")


def _context(pins: GateResultsBronzePins, raw: bytes) -> bytes:
    if type(raw) is not bytes or not 0 < len(raw) <= codec.MAX_BYTES:
        raise codec.Rejected("GATE_RESULTS_SILVER_SNAPSHOT_BYTE_BOUND")
    context = codec.canonical(dict(version=VERSION, pins=asdict(pins), snapshot_hex=raw.hex()))
    if len(context) > MAX_CONTEXT:
        raise codec.Rejected("GATE_RESULTS_SILVER_CONTEXT_BYTE_BOUND")
    return context


def _derive(context: bytes) -> tuple[GateResultsBronzePins, tuple[bytes, ...]]:
    doc = codec.parse(context, MAX_CONTEXT)
    try:
        if set(doc) != {"version", "pins", "snapshot_hex"} or doc["version"] != VERSION:
            raise codec.Rejected("GATE_RESULTS_SILVER_CONTEXT_SCHEMA")
        pins = GateResultsBronzePins(**doc["pins"])
        encoded = doc["snapshot_hex"]
        if (
            type(encoded) is not str
            or not 0 < len(encoded) <= 2 * codec.MAX_BYTES
            or len(encoded) % 2
            or any(c not in "0123456789abcdef" for c in encoded)
        ):
            raise codec.Rejected("GATE_RESULTS_SILVER_SNAPSHOT_HEX_BOUND")
        raw = bytes.fromhex(encoded)
        if _context(pins, raw) != context:
            raise codec.Rejected("GATE_RESULTS_SILVER_CONTEXT_REPLAY_MISMATCH")
        snapshot = codec.replay_snapshot(raw, expected_snapshot_id=pins.snapshot_id)
        if snapshot["source_label"] != pins.source_label:
            raise codec.Rejected("GATE_RESULTS_SILVER_SOURCE_LABEL_MISMATCH")
        records = codec.derive_records(
            raw,
            snapshot_id=pins.snapshot_id,
            capture_event_id=pins.capture_event_id,
            envelope_hash=pins.envelope_hash,
        )
        if (
            type(records) is not tuple
            or not 1 <= len(records) <= codec.MAX_ROWS
            or any(type(r) is not bytes or not 0 < len(r) <= MAX_RECORD for r in records)
            or sum(map(len, records)) > MAX_RECORDS
        ):
            raise codec.Rejected("GATE_RESULTS_SILVER_RECORD_RESOURCE_BOUND")
        return pins, records
    except codec.Rejected:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise codec.Rejected("MALFORMED_GATE_RESULTS_SILVER_CONTEXT") from None


def observe_gate_results_bronze(bronze: Any, *, pins: GateResultsBronzePins) -> bytes:
    """Actual pinned public reader brackets the original full recording read."""
    pins = _pins(pins)
    first = source.read_gate_results_bronze(bronze, **pins.reader_args())
    fingerprint, raw = source.read_recording_bytes(
        bronze,
        source_label=pins.source_label,
        snapshot_id=pins.snapshot_id,
        capture_event_id=pins.capture_event_id,
        envelope_hash=pins.envelope_hash,
    )
    if fingerprint != pins.recording_fingerprint:
        raise codec.Rejected("GATE_RESULTS_SILVER_BRONZE_RECORDING_CHANGED")
    context = _context(pins, raw)
    _, records = _derive(context)
    second = source.read_gate_results_bronze(bronze, **pins.reader_args())
    if first != second or records != first:
        raise codec.Rejected("GATE_RESULTS_SILVER_COMPLETE_BRONZE_OBSERVATION_DRIFT")
    return context


def _revision(context: bytes, records: tuple[bytes, ...]) -> str:
    return codec.sha(
        codec.canonical(
            [
                codec.sha(codec.canonical(DEFINITION)),
                codec.sha(context),
                [codec.sha(r) for r in records],
            ]
        )
    )


def _values(raw: bytes) -> tuple[object, ...]:
    doc = codec.parse(raw, MAX_RECORD)
    fields = doc["stored_fields"]
    if set(fields) != {n for n, _ in SCHEMA}:
        raise codec.Rejected("EXACT_GATE_RESULTS_SCALARS_REQUIRED")
    scalars: list[object] = []
    for name, kind in SCHEMA:
        value = fields[name]
        if kind == "TIMESTAMP WITH TIME ZONE":
            if value is None:
                scalars.append(None)
                continue
            if type(value) is not str:
                raise codec.Rejected("CANONICAL_GATE_RESULTS_INSTANT_REQUIRED")
            instant = datetime.fromisoformat(value)
            if codec.encode_cell(instant, kind) != value:
                raise codec.Rejected("NONCANONICAL_GATE_RESULTS_INSTANT")
            scalars.append(instant)
        else:
            if codec.encode_cell(value, kind) != value:
                raise codec.Rejected("EXACT_GATE_RESULTS_STORED_SCALAR_REQUIRED")
            scalars.append(value)
    return (doc["source_ordinal"], codec.sha(raw), *scalars)


def persist_gate_results_silver(
    bronze: Any,
    target: Any,
    *,
    pins: GateResultsBronzePins,
    expected_context_sha256: str,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    pins = _pins(pins)
    if (
        not codec.pin(expected_context_sha256)
        or not common._actor(actor_id)
        or len(actor_id.encode()) > 128
        or not common._revision(code_revision)
    ):
        raise codec.Rejected("REVIEWED_GATE_RESULTS_SILVER_REQUEST_REQUIRED")
    common._separate(bronze, target)
    _schema(target)
    sets, observations, attempts = (common.name(target, "silver", n) for n in DOMAIN[1:])
    jobs = common.name(target, "medallion_audit", "jobs")
    for table, field, value in (
        (sets, "scope_id", pins.scope_id),
        (attempts, "scope_id", pins.scope_id),
        (jobs, "scope_ref", "sha256:" + pins.scope_id),
        (observations, "source_observation_id", pins.capture_event_id),
    ):
        if target.execute(f'SELECT 1 FROM {table} WHERE "{field}"=? LIMIT 1', [value]).fetchone():
            raise codec.Rejected("GATE_RESULTS_SILVER_FIRST_WRITE_OR_ORPHAN_OBLIGATION")
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref="sha256:" + pins.scope_id,
        config_hash=codec.sha(codec.canonical([DEFINITION, expected_context_sha256])),
    )
    with ledger.execution(job):
        context = observe_gate_results_bronze(bronze, pins=pins)
        if codec.sha(context) != expected_context_sha256:
            raise codec.Rejected("REVIEWED_GATE_RESULTS_SILVER_CONTEXT_CHANGED")
        _, records = _derive(context)
        if observe_gate_results_bronze(bronze, pins=pins) != context:
            raise codec.Rejected("GATE_RESULTS_SILVER_BRONZE_CONTEXT_DRIFT")
        revision = _revision(context, records)
        at = datetime.now(UTC)
        width = len(SCHEMA) + 6
        placeholders = ",".join("?" for _ in range(width))
        target.execute("BEGIN TRANSACTION")
        try:
            target.execute(
                f"INSERT INTO {sets} VALUES (?,?,?,?,?,?)",
                [revision, pins.scope_id, context, len(records), job, at],
            )
            for raw in records:
                target.execute(
                    f"INSERT INTO {observations} VALUES ({placeholders})",
                    [revision, *_values(raw), raw, pins.capture_event_id, at],
                )
            target.execute(f"INSERT INTO {attempts} VALUES (?,?,?)", [job, pins.scope_id, revision])
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise
    fingerprint, _context_bytes, _records = _recording(target, revision)
    return dict(
        revision_id=revision,
        recording_fingerprint=fingerprint,
        row_count=len(records),
        job_id=job,
        decision_eligibility_asserted=False,
    )


def _scalar_queries() -> tuple[str, str, str]:
    selected: list[str] = []
    sizes: list[str] = []
    overflow: list[str] = []
    for field, kind in SCHEMA:
        quoted = '"' + field + '"'
        if kind in ("VARCHAR", "JSON"):
            length = f"octet_length(encode({quoted}))"
            selected.append(f"CASE WHEN {length}<={codec.MAX_CELL} THEN {quoted} END")
            sizes.append(f"coalesce({length},0)")
            overflow.append(f"coalesce({length}>{codec.MAX_CELL},false)")
        else:
            selected.append(quoted)
    overflow += [
        "length(record_id)>64",
        "length(source_observation_id)>64",
        "length(revision_id)>64",
    ]
    return ",".join(selected), "+".join(sizes), " OR ".join(overflow)


def _recording(c: Any, revision: str) -> tuple[str, bytes, tuple[bytes, ...]]:
    if not codec.pin(revision):
        raise codec.Rejected("EXACT_GATE_RESULTS_SILVER_REVISION_REQUIRED")
    c.execute("BEGIN TRANSACTION")
    try:
        _schema(c)
        sets, observations, attempts = (common.name(c, "silver", n) for n in DOMAIN[1:])
        jobs = common.name(c, "medallion_audit", "jobs")
        events = common.name(c, "medallion_audit", "job_events")
        head = c.execute(
            "SELECT CASE WHEN length(scope_id)<=64 THEN scope_id END,"
            "CASE WHEN octet_length(context)<=? THEN context END,row_count,"
            "CASE WHEN length(first_job_id)<=128 THEN first_job_id END,recorded_at "
            f"FROM {sets} WHERE revision_id=?",
            [MAX_CONTEXT, revision],
        ).fetchone()
        if head is None or any(head[i] is None for i in (0, 1, 3)):
            raise codec.Rejected("GATE_RESULTS_SILVER_SET_MISSING_OR_UNBOUNDED")
        context = bytes(head[1])
        pins, expected = _derive(context)
        selected, size, overflow = _scalar_queries()
        predicate = "revision_id=? OR source_observation_id=?"
        args = [revision, pins.capture_event_id]
        totals = c.execute(
            "SELECT count(*),coalesce(sum(octet_length(record_bytes)),0),"
            "coalesce(max(octet_length(record_bytes)),0),"
            f"coalesce(sum({size}),0),coalesce(bool_or({overflow}),false) "
            f"FROM {observations} WHERE {predicate}",
            args,
        ).fetchone()
        if (
            totals is None
            or not 1 <= totals[0] <= codec.MAX_ROWS
            or totals[1] > MAX_RECORDS
            or totals[2] > MAX_RECORD
            or totals[3] > MAX_SCALAR_BYTES
            or totals[4]
        ):
            raise codec.Rejected("GATE_RESULTS_SILVER_TRANSFER_BOUND")
        stored = c.execute(
            "SELECT CASE WHEN length(revision_id)<=64 THEN revision_id END,ordinal,"
            f"CASE WHEN length(record_id)<=64 THEN record_id END,{selected},"
            "CASE WHEN octet_length(record_bytes)<=? THEN record_bytes END,"
            "CASE WHEN length(source_observation_id)<=64 THEN source_observation_id END,"
            "recorded_at "
            f"FROM {observations} WHERE {predicate} ORDER BY ordinal LIMIT {codec.MAX_ROWS + 1}",
            [MAX_RECORD, *args],
        ).fetchall()
        links = c.execute(
            "SELECT CASE WHEN length(job_id)<=128 THEN job_id END,"
            "CASE WHEN length(scope_id)<=64 THEN scope_id END,"
            f"CASE WHEN length(revision_id)<=64 THEN revision_id END FROM {attempts} "
            "WHERE scope_id=? OR revision_id=? OR job_id=? LIMIT 3",
            [head[0], revision, head[3]],
        ).fetchall()
        scoped = common._metadata(
            c,
            "SELECT CASE WHEN length(job_id)<=128 THEN job_id END,"
            "CASE WHEN parent_job_id IS NULL THEN NULL ELSE 'PRESENT' END,"
            "CASE WHEN length(command_name)<=128 THEN command_name END,"
            "CASE WHEN octet_length(encode(actor_id))<=128 THEN actor_id END,"
            "CASE WHEN length(code_revision)<=40 THEN code_revision END,"
            "CASE WHEN length(config_hash)<=64 THEN config_hash END,"
            f"CASE WHEN length(scope_ref)<=71 THEN scope_ref END,created_at FROM {jobs} "
            "WHERE scope_ref=? OR job_id=?",
            ["sha256:" + head[0], head[3]],
            1,
        )
        history = common._metadata(
            c,
            "SELECT event_index,CASE WHEN length(state)<=32 THEN state END,recorded_at,"
            "CASE WHEN reason_code IS NULL THEN NULL ELSE 'PRESENT' END "
            f"FROM {events} WHERE job_id=? ORDER BY event_index",
            [head[3]],
            3,
        )
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK")
        raise
    if (
        pins.scope_id != head[0]
        or _revision(context, expected) != revision
        or head[2] != len(expected)
        or len(stored) != len(expected)
        or links != [(head[3], pins.scope_id, revision)]
    ):
        raise codec.Rejected("GATE_RESULTS_SILVER_SET_OR_COMPLETE_COVERAGE_MISMATCH")
    width = len(SCHEMA) + 3
    scalar_metadata: list[object] = []
    for got, raw in zip(stored, expected, strict=True):
        if (
            type(got[1]) is not int
            or got[:width] != (revision, *_values(raw))
            or got[width] is None
            or bytes(got[width]) != raw
            or got[width + 1 :] != (pins.capture_event_id, head[4])
        ):
            raise codec.Rejected("GATE_RESULTS_SILVER_FULL_RECORD_RECOMPUTATION_MISMATCH")
        scalars = [
            codec.encode_cell(v, kind) for v, (_n, kind) in zip(got[3:width], SCHEMA, strict=True)
        ]
        scalar_metadata.append([*got[:3], scalars, codec.sha(raw), *got[width + 1 :]])
    config = codec.sha(codec.canonical([DEFINITION, codec.sha(context)]))
    if (
        len(scoped) != 1
        or scoped[0][0] != head[3]
        or scoped[0][1] is not None
        or scoped[0][2] != COMMAND
        or not common._actor(scoped[0][3])
        or not common._revision(scoped[0][4])
        or scoped[0][5] != config
        or scoped[0][6] != "sha256:" + pins.scope_id
        or [(h[0], h[1], h[3]) for h in history]
        != [(1, "PLANNED", None), (2, "RUNNING", None), (3, "SUCCEEDED", None)]
    ):
        raise codec.Rejected("ORIGINAL_GATE_RESULTS_SILVER_AUDIT_NOT_VERIFIED")
    for clock in [head[4], scoped[0][7], *(h[2] for h in history)]:
        common._clock(clock)
    metadata = [
        VERSION,
        revision,
        head[0],
        codec.sha(context),
        list(head[2:]),
        scalar_metadata,
        links,
        scoped,
        history,
    ]
    return codec.sha(common._json(metadata)), context, expected


def read_gate_results_silver(
    silver: Any, *, revision_id: str, expected_recording_fingerprint: str
) -> tuple[bytes, ...]:
    if not codec.pin(expected_recording_fingerprint):
        raise codec.Rejected("EXACT_GATE_RESULTS_SILVER_RECORDING_PIN_REQUIRED")
    common._readonly(silver)
    fingerprint, _context_bytes, records = _recording(silver, revision_id)
    if fingerprint != expected_recording_fingerprint:
        raise codec.Rejected("GATE_RESULTS_SILVER_RECORDING_FINGERPRINT_CHANGED")
    return records


def revalidate_gate_results_silver(
    bronze: Any, silver: Any, *, revision_id: str, expected_recording_fingerprint: str
) -> tuple[bytes, ...]:
    common._separate(bronze, silver)
    args = dict(
        revision_id=revision_id, expected_recording_fingerprint=expected_recording_fingerprint
    )
    first = read_gate_results_silver(silver, **args)
    fingerprint, context, _records = _recording(silver, revision_id)
    if fingerprint != expected_recording_fingerprint:
        raise codec.Rejected("GATE_RESULTS_SILVER_RECORDING_FINGERPRINT_CHANGED")
    pins, _records = _derive(context)
    for _ in range(2):
        if observe_gate_results_bronze(bronze, pins=pins) != context:
            raise codec.Rejected("CURRENT_GATE_RESULTS_BRONZE_CONTEXT_CHANGED")
    if read_gate_results_silver(silver, **args) != first:
        raise codec.Rejected("GATE_RESULTS_SILVER_CHANGED_DURING_REVALIDATION")
    return first


def revalidate_gate_results_silver_source(
    legacy: Any,
    bronze: Any,
    silver: Any,
    *,
    revision_id: str,
    expected_recording_fingerprint: str,
) -> tuple[bytes, ...]:
    for left, right in ((legacy, bronze), (legacy, silver), (bronze, silver)):
        common._separate(left, right)
    args = dict(
        revision_id=revision_id, expected_recording_fingerprint=expected_recording_fingerprint
    )
    first = revalidate_gate_results_silver(bronze, silver, **args)
    _fingerprint, context, _records = _recording(silver, revision_id)
    pins, expected = _derive(context)
    observed = source.revalidate_gate_results_source(legacy, bronze, **pins.reader_args())
    if observed != expected or revalidate_gate_results_silver(bronze, silver, **args) != first:
        raise codec.Rejected("CURRENT_LEGACY_GATE_RESULTS_OR_SILVER_CHANGED")
    return first
