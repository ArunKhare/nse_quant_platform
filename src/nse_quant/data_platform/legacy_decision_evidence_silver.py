"""Audited persisted decision-evidence Silver; naive wall fields remain timezone-unknown."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform import legacy_decision_evidence_bronze as source
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy

codec = source.codec
common = source.common
VERSION = "legacy-decision-evidence-silver-recording@1"
COMMAND = "normalize.legacy_decision_evidence@1"
MAX_CONTEXT_BYTES = 2200000
MAX_RECORD_BYTES = 524288
MAX_RECORD_TOTAL_BYTES = 4194304
MAX_SCALAR_BYTES = 1048576
MAX_ROWS = 1000
DOMAIN = (
    "decision_evidence_versions",
    "decision_evidence_sets",
    "decision_evidence_observations",
    "decision_evidence_attempts",
)
TABLES = {("silver", n) for n in DOMAIN} | {
    ("medallion_audit", n) for n in ("schema_versions", "dataset_contracts", "jobs", "job_events")
}
CONTRACT = DatasetContract(
    "silver.legacy_decision_evidence_observations",
    "1",
    Layer.SILVER,
    WritePolicy.APPEND_REVISIONS,
    ("revision_id", "ordinal"),
    ("revision_id", "ordinal", "source_observation_id", "recorded_at", "record_bytes"),
    "native_retained_legacy_decision_evidence",
)
DEFINITION = (
    VERSION,
    COMMAND,
    codec.DEFINITION,
    source.DEFINITION,
    CONTRACT.canonical_json(),
    MAX_CONTEXT_BYTES,
    MAX_RECORD_BYTES,
    MAX_RECORD_TOTAL_BYTES,
    MAX_SCALAR_BYTES,
    MAX_ROWS,
    "seven exact retained scalars; naive TIMESTAMP wall tuple is never an aware instant",
    "opaque payload TEXT; retained available bool is not independently verified availability",
    "complete original snapshot and every ordinal; original audit obligations cannot heal",
    "scope source-label+capture-event excludes snapshot/envelope/recording/context review pins",
)


@dataclass(frozen=True)
class DecisionEvidenceBronzePins:
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
            raise codec.Rejected("EXACT_DECISION_EVIDENCE_BRONZE_PINS_REQUIRED")

    @property
    def scope_id(self) -> str:
        return codec.sha(codec.canonical([VERSION, self.source_label, self.capture_event_id]))

    def reader_args(self) -> dict[str, str]:
        return dict(
            source_label=self.source_label,
            snapshot_id=self.snapshot_id,
            capture_event_id=self.capture_event_id,
            envelope_hash=self.envelope_hash,
            expected_recording_fingerprint=self.recording_fingerprint,
        )


def _pins(value: DecisionEvidenceBronzePins) -> DecisionEvidenceBronzePins:
    if type(value) is not DecisionEvidenceBronzePins:
        raise codec.Rejected("TYPED_DECISION_EVIDENCE_BRONZE_PINS_REQUIRED")
    return DecisionEvidenceBronzePins(**asdict(value))


def _owned(c: Any, *, complete: bool) -> None:
    paths = c.execute(
        "SELECT path FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall()
    if len(paths) != 1 or not paths[0][0]:
        raise codec.Rejected("FILE_BACKED_DECISION_EVIDENCE_SILVER_REQUIRED")
    rows = c.execute(
        "SELECT CASE WHEN octet_length(encode(table_schema))<=128 THEN table_schema END,"
        "CASE WHEN octet_length(encode(table_name))<=128 THEN table_name END,table_type "
        "FROM information_schema.tables WHERE table_catalog=current_database() LIMIT 9"
    ).fetchall()
    known = {(s, t) for s, t, _kind in rows}
    if (
        known - TABLES
        or any(kind != "BASE TABLE" for _, _, kind in rows)
        or complete
        and known != TABLES
    ):
        raise codec.Rejected("DEDICATED_DECISION_EVIDENCE_SILVER_REQUIRED")


def initialize_decision_evidence_silver(c: Any) -> None:
    """Explicit empty dedicated target; partial initialization is not adopted."""
    _owned(c, complete=False)
    if c.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() LIMIT 1"
    ).fetchone():
        raise codec.Rejected("EMPTY_DECISION_EVIDENCE_SILVER_INITIALIZATION_REQUIRED")
    AuditLedger(c).initialize()
    versions, sets, records, attempts = (common.name(c, "silver", n) for n in DOMAIN)
    scalars = ",".join(f'"{n}" {kind} NOT NULL' for n, kind in codec.SCHEMA)
    c.execute("BEGIN TRANSACTION")
    try:
        c.execute(f"CREATE SCHEMA {versions.rsplit('.', 1)[0]}")
        c.execute(f"CREATE TABLE {versions} (version INTEGER PRIMARY KEY,definition BLOB NOT NULL)")
        c.execute(f"INSERT INTO {versions} VALUES (1,?)", [codec.canonical(DEFINITION)])
        c.execute(
            f"CREATE TABLE {sets} (revision_id VARCHAR PRIMARY KEY,"
            "scope_id VARCHAR UNIQUE NOT NULL,context BLOB NOT NULL,"
            "row_count INTEGER NOT NULL,"
            "first_job_id VARCHAR NOT NULL,recorded_at TIMESTAMPTZ NOT NULL)"
        )
        c.execute(
            f"CREATE TABLE {records} (revision_id VARCHAR NOT NULL,ordinal INTEGER NOT NULL,"
            "record_id VARCHAR NOT NULL," + scalars + ",record_bytes BLOB NOT NULL,"
            "source_observation_id VARCHAR NOT NULL,recorded_at TIMESTAMPTZ NOT NULL,"
            "PRIMARY KEY(revision_id,ordinal))"
        )
        c.execute(
            f"CREATE TABLE {attempts} (job_id VARCHAR PRIMARY KEY,scope_id VARCHAR NOT NULL,"
            "revision_id VARCHAR NOT NULL)"
        )
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK")
        raise
    AuditLedger(c).register_contract(CONTRACT)


def _schema(c: Any) -> None:
    _owned(c, complete=True)
    versions = common.name(c, "silver", DOMAIN[0])
    contracts = common.name(c, "medallion_audit", "dataset_contracts")
    audit = common.name(c, "medallion_audit", "schema_versions")
    if c.execute(
        f"SELECT version,CASE WHEN octet_length(definition)<=32768 THEN definition END "
        f"FROM {versions} LIMIT 2"
    ).fetchall() != [(1, codec.canonical(DEFINITION))]:
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_DEFINITION_DRIFT")
    if c.execute(
        "SELECT CASE WHEN length(fingerprint)<=64 THEN fingerprint END,"
        f"CASE WHEN octet_length(encode(contract_json))<=32768 THEN contract_json END "
        f"FROM {contracts} WHERE dataset_name=? AND contract_version='1'",
        [CONTRACT.name],
    ).fetchall() != [(CONTRACT.fingerprint, CONTRACT.canonical_json())]:
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_CONTRACT_DRIFT")
    if c.execute(f"SELECT version FROM {audit} LIMIT 2").fetchall() != [(1,)]:
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_AUDIT_SCHEMA_DRIFT")
    expected = [
        ("revision_id", "VARCHAR"),
        ("ordinal", "INTEGER"),
        ("record_id", "VARCHAR"),
        *codec.SCHEMA,
        ("record_bytes", "BLOB"),
        ("source_observation_id", "VARCHAR"),
        ("recorded_at", "TIMESTAMP WITH TIME ZONE"),
    ]
    actual = c.execute(
        "SELECT CASE WHEN length(column_name)<=128 THEN column_name END,"
        "CASE WHEN length(data_type)<=128 THEN data_type END,is_nullable "
        "FROM information_schema.columns WHERE table_catalog=current_database() "
        "AND table_schema='silver' AND table_name=? ORDER BY ordinal_position LIMIT ?",
        [DOMAIN[2], len(expected) + 1],
    ).fetchall()
    if actual != [(n, kind, "NO") for n, kind in expected]:
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_SCALAR_SCHEMA_DRIFT")


def _context(pins: DecisionEvidenceBronzePins, raw: bytes) -> bytes:
    if type(raw) is not bytes or not 0 < len(raw) <= codec.MAX_BYTES:
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_SNAPSHOT_BYTE_BOUND")
    result = codec.canonical(dict(version=VERSION, pins=asdict(pins), snapshot_hex=raw.hex()))
    if len(result) > MAX_CONTEXT_BYTES:
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_CONTEXT_BYTE_BOUND")
    return result


def _derive(context: bytes) -> tuple[DecisionEvidenceBronzePins, tuple[bytes, ...]]:
    doc = codec.parse(context, MAX_CONTEXT_BYTES)
    try:
        if set(doc) != {"version", "pins", "snapshot_hex"} or doc["version"] != VERSION:
            raise codec.Rejected("DECISION_EVIDENCE_SILVER_CONTEXT_SCHEMA")
        pins = DecisionEvidenceBronzePins(**doc["pins"])
        encoded = doc["snapshot_hex"]
        if (
            type(encoded) is not str
            or not 0 < len(encoded) <= 2 * codec.MAX_BYTES
            or len(encoded) % 2
            or any(c not in "0123456789abcdef" for c in encoded)
        ):
            raise codec.Rejected("DECISION_EVIDENCE_SILVER_SNAPSHOT_HEX_BOUND")
        raw = bytes.fromhex(encoded)
        if _context(pins, raw) != context:
            raise codec.Rejected("DECISION_EVIDENCE_SILVER_EXACT_CONTEXT_REQUIRED")
        artifact = codec.replay_snapshot(raw, expected_snapshot_id=pins.snapshot_id)
        if artifact["source_label"] != pins.source_label:
            raise codec.Rejected("DECISION_EVIDENCE_SILVER_SOURCE_LABEL_MISMATCH")
        records = codec.derive_records(
            raw,
            snapshot_id=pins.snapshot_id,
            capture_event_id=pins.capture_event_id,
            envelope_hash=pins.envelope_hash,
        )
        if (
            not 1 <= len(records) <= MAX_ROWS
            or any(type(r) is not bytes or not 0 < len(r) <= MAX_RECORD_BYTES for r in records)
            or sum(map(len, records)) > MAX_RECORD_TOTAL_BYTES
        ):
            raise codec.Rejected("DECISION_EVIDENCE_SILVER_RECORD_BYTE_OR_COUNT_BOUND")
        return pins, records
    except codec.Rejected:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_CONTEXT_MALFORMED") from None


def observe_decision_evidence_bronze(bronze: Any, *, pins: DecisionEvidenceBronzePins) -> bytes:
    """Actual pinned public reader brackets original full-payload/native-recording read."""
    pins = _pins(pins)
    first = source.read_decision_evidence_bronze(bronze, **pins.reader_args())
    fingerprint, raw = source.read_recording_bytes(
        bronze,
        source_label=pins.source_label,
        snapshot_id=pins.snapshot_id,
        capture_event_id=pins.capture_event_id,
        envelope_hash=pins.envelope_hash,
    )
    if fingerprint != pins.recording_fingerprint:
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_BRONZE_RECORDING_CHANGED")
    context = _context(pins, raw)
    _checked, records = _derive(context)
    second = source.read_decision_evidence_bronze(bronze, **pins.reader_args())
    if first != second or records != first:
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_NATIVE_SOURCE_DRIFT")
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
    doc = codec.parse(raw, MAX_RECORD_BYTES)
    fields = doc["stored_fields"]
    values: list[object] = []
    for field, kind in codec.SCHEMA:
        value = fields[field]
        if kind == "TIMESTAMP":
            value = datetime.fromisoformat(value)
            if codec.wall_fields(value) != fields[field]:
                raise codec.Rejected("DECISION_EVIDENCE_SILVER_EXACT_NAIVE_WALL_REQUIRED")
        values.append(value)
    return doc["source_ordinal"], codec.sha(raw), *values


def persist_decision_evidence_silver(
    bronze: Any,
    target: Any,
    *,
    pins: DecisionEvidenceBronzePins,
    expected_context_sha256: str,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    pins = _pins(pins)
    if (
        not codec.pin(expected_context_sha256)
        or not common._actor(actor_id)
        or not common._revision(code_revision)
    ):
        raise codec.Rejected("REVIEWED_DECISION_EVIDENCE_SILVER_REQUEST_REQUIRED")
    common._separate(bronze, target)
    _schema(target)
    sets, records, attempts = (common.name(target, "silver", n) for n in DOMAIN[1:])
    jobs = common.name(target, "medallion_audit", "jobs")
    for table, field, value in (
        (sets, "scope_id", pins.scope_id),
        (attempts, "scope_id", pins.scope_id),
        (jobs, "scope_ref", "sha256:" + pins.scope_id),
        (records, "source_observation_id", pins.capture_event_id),
    ):
        if target.execute(f'SELECT 1 FROM {table} WHERE "{field}"=? LIMIT 1', [value]).fetchone():
            raise codec.Rejected("DECISION_EVIDENCE_SILVER_FIRST_WRITE_OR_ORPHAN_OBLIGATION")
    ledger = AuditLedger(target)
    config = codec.sha(codec.canonical([DEFINITION, expected_context_sha256]))
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref="sha256:" + pins.scope_id,
        config_hash=config,
    )
    with ledger.execution(job):
        context = observe_decision_evidence_bronze(bronze, pins=pins)
        if codec.sha(context) != expected_context_sha256:
            raise codec.Rejected("REVIEWED_DECISION_EVIDENCE_CONTEXT_CHANGED")
        _checked, projected = _derive(context)
        if observe_decision_evidence_bronze(bronze, pins=pins) != context:
            raise codec.Rejected("DECISION_EVIDENCE_SILVER_BRONZE_CONTEXT_DRIFT")
        revision = _revision(context, projected)
        at = datetime.now(UTC)
        placeholders = ",".join("?" for _ in range(len(codec.SCHEMA) + 6))
        target.execute("BEGIN TRANSACTION")
        try:
            target.execute(
                f"INSERT INTO {sets} VALUES (?,?,?,?,?,?)",
                [revision, pins.scope_id, context, len(projected), job, at],
            )
            for raw in projected:
                target.execute(
                    f"INSERT INTO {records} VALUES ({placeholders})",
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
        row_count=len(projected),
        job_id=job,
        decision_eligibility_asserted=False,
    )


def _scalar_queries() -> tuple[str, str, str]:
    selected: list[str] = []
    lengths: list[str] = []
    overflow: list[str] = []
    for field, kind in codec.SCHEMA:
        quoted = '"' + field + '"'
        if kind == "VARCHAR":
            size = f"octet_length(encode({quoted}))"
            selected.append(f"CASE WHEN {size}<={codec.MAX_CELL} THEN {quoted} END")
            lengths.append(f"coalesce({size},0)")
            overflow.append(f"coalesce({size}>{codec.MAX_CELL},false)")
        else:
            selected.append(quoted)
    overflow.extend(("length(record_id)>64", "length(source_observation_id)>64"))
    return ",".join(selected), "+".join(lengths), " OR ".join(overflow)


def _recording(c: Any, revision: str) -> tuple[str, bytes, tuple[bytes, ...]]:
    if not codec.pin(revision):
        raise codec.Rejected("EXACT_DECISION_EVIDENCE_SILVER_REVISION_REQUIRED")
    c.execute("BEGIN TRANSACTION")
    try:
        _schema(c)
        sets, observations, attempts = (common.name(c, "silver", n) for n in DOMAIN[1:])
        jobs = common.name(c, "medallion_audit", "jobs")
        events = common.name(c, "medallion_audit", "job_events")
        row = c.execute(
            f"SELECT CASE WHEN length(scope_id)<=64 THEN scope_id END,"
            "CASE WHEN octet_length(context)<=? THEN context END,row_count,"
            f"CASE WHEN length(first_job_id)<=128 THEN first_job_id END,recorded_at "
            f"FROM {sets} WHERE revision_id=? LIMIT 2",
            [MAX_CONTEXT_BYTES, revision],
        ).fetchall()
        if len(row) != 1:
            raise codec.Rejected("DECISION_EVIDENCE_SILVER_EXACT_SET_REQUIRED")
        row = row[0]
        if row[0] is None or row[1] is None or row[3] is None:
            raise codec.Rejected("DECISION_EVIDENCE_SILVER_SET_MISSING_OR_UNBOUNDED")
        coverage = c.execute(
            f"SELECT count(*) FROM {sets} WHERE revision_id=? OR scope_id=?",
            [revision, row[0]],
        ).fetchone()
        if coverage != (1,):
            raise codec.Rejected("DECISION_EVIDENCE_SILVER_SET_COVERAGE_MISMATCH")
        context = bytes(row[1])
        pins, expected = _derive(context)
        selected, scalar_bytes, overflow = _scalar_queries()
        totals = c.execute(
            f"SELECT count(*),coalesce(sum(octet_length(record_bytes)),0),"
            f"coalesce(max(octet_length(record_bytes)),0),coalesce(sum({scalar_bytes}),0),"
            f"coalesce(bool_or({overflow}),false) FROM {observations} "
            "WHERE revision_id=? OR source_observation_id=?",
            [revision, pins.capture_event_id],
        ).fetchone()
        if (
            totals is None
            or not 1 <= totals[0] <= MAX_ROWS
            or totals[1] > MAX_RECORD_TOTAL_BYTES
            or totals[2] > MAX_RECORD_BYTES
            or totals[3] > MAX_SCALAR_BYTES
            or totals[4]
        ):
            raise codec.Rejected("DECISION_EVIDENCE_SILVER_TRANSFER_BOUND")
        stored = c.execute(
            "SELECT CASE WHEN length(revision_id)<=64 THEN revision_id END,ordinal,"
            f"CASE WHEN length(record_id)<=64 THEN record_id END,{selected},"
            "CASE WHEN octet_length(record_bytes)<=? THEN record_bytes END,"
            "CASE WHEN length(source_observation_id)<=64 THEN source_observation_id END,"
            f"recorded_at FROM {observations} WHERE revision_id=? OR source_observation_id=? "
            "ORDER BY ordinal LIMIT ?",
            [MAX_RECORD_BYTES, revision, pins.capture_event_id, MAX_ROWS + 1],
        ).fetchall()
        links = c.execute(
            "SELECT CASE WHEN length(job_id)<=128 THEN job_id END,"
            "CASE WHEN length(scope_id)<=64 THEN scope_id END,"
            f"CASE WHEN length(revision_id)<=64 THEN revision_id END FROM {attempts} "
            "WHERE scope_id=? OR revision_id=? OR job_id=? LIMIT 3",
            [row[0], revision, row[3]],
        ).fetchall()
        scoped = common._metadata(
            c,
            "SELECT CASE WHEN length(job_id)<=128 THEN job_id END,"
            "CASE WHEN parent_job_id IS NULL THEN NULL ELSE 'PRESENT' END,"
            "CASE WHEN length(command_name)<=128 THEN command_name END,"
            "CASE WHEN length(actor_id)<=128 THEN actor_id END,"
            "CASE WHEN length(code_revision)<=40 THEN code_revision END,"
            "CASE WHEN length(config_hash)<=64 THEN config_hash END,"
            f"CASE WHEN length(scope_ref)<=71 THEN scope_ref END,created_at FROM {jobs} "
            "WHERE scope_ref=? OR job_id=?",
            ["sha256:" + row[0], row[3]],
            1,
        )
        history = common._metadata(
            c,
            "SELECT event_index,CASE WHEN length(state)<=32 THEN state END,recorded_at,"
            f"CASE WHEN reason_code IS NULL THEN NULL ELSE 'PRESENT' END FROM {events} "
            "WHERE job_id=? ORDER BY event_index",
            [row[3]],
            3,
        )
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK")
        raise
    if (
        row[0] != pins.scope_id
        or row[2] != len(expected)
        or len(stored) != len(expected)
        or _revision(context, expected) != revision
        or links != [(row[3], pins.scope_id, revision)]
    ):
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_COMPLETE_COVERAGE_MISMATCH")
    width = len(codec.SCHEMA) + 3
    scalar_metadata: list[object] = []
    for got, raw in zip(stored, expected, strict=True):
        if (
            type(got[1]) is not int
            or got[:width] != (revision, *_values(raw))
            or got[width] is None
            or bytes(got[width]) != raw
            or got[width + 1 :] != (pins.capture_event_id, row[4])
        ):
            raise codec.Rejected("DECISION_EVIDENCE_SILVER_FULL_RECORD_RECOMPUTATION_MISMATCH")
        # Encode source naive wall values BEFORE the aware native metadata serializer.
        scalars = [
            codec.encode_cell(v, kind)
            for v, (_n, kind) in zip(got[3:width], codec.SCHEMA, strict=True)
        ]
        scalar_metadata.append([*got[:3], scalars, codec.sha(raw), *got[width + 1 :]])
    config = codec.sha(codec.canonical([DEFINITION, codec.sha(context)]))
    if (
        len(scoped) != 1
        or scoped[0][0] != row[3]
        or scoped[0][1] is not None
        or scoped[0][2] != COMMAND
        or not common._actor(scoped[0][3])
        or not common._revision(scoped[0][4])
        or scoped[0][5] != config
        or scoped[0][6] != "sha256:" + pins.scope_id
        or [(h[0], h[1], h[3]) for h in history]
        != [(1, "PLANNED", None), (2, "RUNNING", None), (3, "SUCCEEDED", None)]
    ):
        raise codec.Rejected("ORIGINAL_DECISION_EVIDENCE_SILVER_AUDIT_NOT_VERIFIED")
    for at in [row[4], scoped[0][7], *(h[2] for h in history)]:
        common._clock(at)
    metadata = [
        VERSION,
        revision,
        row[0],
        codec.sha(context),
        list(row[2:]),
        scalar_metadata,
        links,
        scoped,
        history,
    ]
    return codec.sha(common._json(metadata)), context, expected


def read_decision_evidence_silver(
    c: Any, *, revision_id: str, expected_recording_fingerprint: str
) -> tuple[bytes, ...]:
    if not codec.pin(expected_recording_fingerprint):
        raise codec.Rejected("EXACT_DECISION_EVIDENCE_SILVER_RECORDING_PIN_REQUIRED")
    common._readonly(c)
    fingerprint, _context_bytes, records = _recording(c, revision_id)
    if fingerprint != expected_recording_fingerprint:
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_RECORDING_FINGERPRINT_CHANGED")
    return records


def revalidate_decision_evidence_silver(
    bronze: Any, silver: Any, *, revision_id: str, expected_recording_fingerprint: str
) -> tuple[bytes, ...]:
    common._separate(bronze, silver)
    args = dict(
        revision_id=revision_id, expected_recording_fingerprint=expected_recording_fingerprint
    )
    first = read_decision_evidence_silver(silver, **args)
    fingerprint, context, _records = _recording(silver, revision_id)
    if fingerprint != expected_recording_fingerprint:
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_RECORDING_FINGERPRINT_CHANGED")
    pins, _records = _derive(context)
    for _ in range(2):
        if observe_decision_evidence_bronze(bronze, pins=pins) != context:
            raise codec.Rejected("CURRENT_DECISION_EVIDENCE_BRONZE_CONTEXT_CHANGED")
    if read_decision_evidence_silver(silver, **args) != first:
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_CHANGED_DURING_REVALIDATION")
    return first


def revalidate_decision_evidence_silver_source(
    legacy: Any,
    bronze: Any,
    silver: Any,
    *,
    revision_id: str,
    expected_recording_fingerprint: str,
) -> tuple[bytes, ...]:
    common._separate(legacy, silver)
    args = dict(
        revision_id=revision_id, expected_recording_fingerprint=expected_recording_fingerprint
    )
    first = revalidate_decision_evidence_silver(bronze, silver, **args)
    _fingerprint, context, _records = _recording(silver, revision_id)
    pins, _records = _derive(context)
    actual = source.revalidate_decision_evidence_source(legacy, bronze, **pins.reader_args())
    if actual != first or read_decision_evidence_silver(silver, **args) != first:
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_CURRENT_SOURCE_DRIFT")
    return first
