"""Audited persisted retained feature Silver, never recomputed Gold or admission."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from typing import Any

from nse_quant.data_platform import legacy_daily_rv_bronze as common
from nse_quant.data_platform import legacy_feature_snapshot_bronze as source
from nse_quant.data_platform import legacy_feature_snapshots as codec
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy

VERSION = "legacy-feature-snapshot-silver-recording@1"
COMMAND = "normalize.legacy_feature_snapshots@1"
MAX_CONTEXT = 2200000
MAX_SCALAR_BYTES = codec.MAX_BYTES
CONTRACT = DatasetContract(
    "silver.legacy_feature_observations",
    "1",
    Layer.SILVER,
    WritePolicy.APPEND_REVISIONS,
    ("revision_id", "ordinal"),
    ("revision_id", "ordinal", "recorded_at", "source_observation_id", "record_bytes"),
    "native_legacy_feature_snapshot_silver",
)
DEFINITION = (
    VERSION,
    COMMAND,
    codec.DEFINITION,
    source.DEFINITION,
    CONTRACT.canonical_json(),
    MAX_CONTEXT,
    MAX_SCALAR_BYTES,
    "all 22 retained scalars; DOUBLE hex, BIGINT exact, nullable dates/instants",
    "diagnostics stored text, not interpreted or normalized",
)
TABLES = {
    ("silver", t)
    for t in ("feature_versions", "feature_sets", "feature_observations", "feature_attempts")
}
TABLES |= {
    ("medallion_audit", t) for t in ("schema_versions", "dataset_contracts", "jobs", "job_events")
}


@dataclass(frozen=True)
class FeatureBronzePins:
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
            raise codec.Rejected("EXACT_FEATURE_BRONZE_PINS_REQUIRED")

    @property
    def scope_id(self) -> str:
        return codec.sha(
            codec.canonical([VERSION, self.source_label, self.snapshot_id, self.capture_event_id])
        )

    def reader_args(self) -> dict[str, str]:
        return dict(
            source_label=self.source_label,
            snapshot_id=self.snapshot_id,
            capture_event_id=self.capture_event_id,
            envelope_hash=self.envelope_hash,
            expected_recording_fingerprint=self.recording_fingerprint,
        )


def _pins(value: FeatureBronzePins) -> FeatureBronzePins:
    if type(value) is not FeatureBronzePins:
        raise codec.Rejected("TYPED_FEATURE_BRONZE_PINS_REQUIRED")
    return FeatureBronzePins(**asdict(value))


def _owned(conn: Any, *, complete: bool) -> None:
    paths = conn.execute(
        "SELECT path FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall()
    if len(paths) != 1 or not paths[0][0]:
        raise codec.Rejected("FILE_BACKED_FEATURE_SILVER_REQUIRED")
    rows = conn.execute(
        "SELECT CASE WHEN octet_length(encode(table_schema))<=128 THEN table_schema END,"
        "CASE WHEN octet_length(encode(table_name))<=128 THEN table_name END,table_type "
        "FROM information_schema.tables "
        "WHERE table_catalog=current_database() LIMIT 9"
    ).fetchall()
    known = {(s, t) for s, t, _ in rows}
    if (
        known - TABLES
        or any(k != "BASE TABLE" for _, _, k in rows)
        or (complete and known != TABLES)
    ):
        raise codec.Rejected("DEDICATED_FEATURE_SILVER_REQUIRED")


def initialize_feature_snapshot_silver(target: Any) -> None:
    """Explicit empty dedicated target; never repairs/adopts partial initialization."""
    _owned(target, complete=False)
    if target.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() LIMIT 1"
    ).fetchone():
        raise codec.Rejected("EMPTY_FEATURE_SILVER_INITIALIZATION_REQUIRED")
    AuditLedger(target).initialize()

    def n(table: str) -> str:
        return common.name(target, "silver", table)

    scalars = []
    for field, kind in codec.SCHEMA:
        sql_type = "VARCHAR" if kind in ("DOUBLE", "JSON") else kind
        required = " NOT NULL" if field == "feature_id" else ""
        scalars.append(f'"{field}" {sql_type}{required}')
    target.execute("BEGIN TRANSACTION")
    try:
        target.execute(f"CREATE SCHEMA {n('feature_versions').rsplit('.', 1)[0]}")
        target.execute(
            f"CREATE TABLE {n('feature_versions')} (version INTEGER PRIMARY KEY,"
            "definition BLOB NOT NULL)"
        )
        target.execute(
            f"INSERT INTO {n('feature_versions')} VALUES (1,?)", [codec.canonical(DEFINITION)]
        )
        target.execute(
            f"CREATE TABLE {n('feature_sets')} (revision_id VARCHAR PRIMARY KEY,"
            "scope_id VARCHAR UNIQUE NOT NULL,context BLOB NOT NULL,row_count INTEGER "
            "NOT NULL,first_job_id VARCHAR NOT NULL,recorded_at TIMESTAMPTZ NOT NULL)"
        )
        target.execute(
            f"CREATE TABLE {n('feature_observations')} (revision_id VARCHAR NOT NULL,"
            "ordinal INTEGER NOT NULL,record_id VARCHAR NOT NULL,"
            + ",".join(scalars)
            + ",record_bytes BLOB NOT NULL,"
            "source_observation_id VARCHAR NOT NULL,recorded_at TIMESTAMPTZ NOT NULL,"
            "PRIMARY KEY(revision_id,ordinal))"
        )
        target.execute(
            f"CREATE TABLE {n('feature_attempts')} (job_id VARCHAR PRIMARY KEY,"
            "scope_id VARCHAR NOT NULL,revision_id VARCHAR NOT NULL)"
        )
        target.execute("COMMIT")
    except BaseException:
        target.execute("ROLLBACK")
        raise
    AuditLedger(target).register_contract(CONTRACT)


def _schema(conn: Any) -> None:
    _owned(conn, complete=True)
    versions = common.name(conn, "silver", "feature_versions")
    if conn.execute(
        f"SELECT version,CASE WHEN octet_length(definition)<=32768 THEN definition END "
        f"FROM {versions} LIMIT 2"
    ).fetchall() != [(1, codec.canonical(DEFINITION))]:
        raise codec.Rejected("FEATURE_SILVER_DEFINITION_DRIFT")
    contracts = common.name(conn, "medallion_audit", "dataset_contracts")
    if conn.execute(
        f"SELECT CASE WHEN length(fingerprint)<=64 THEN fingerprint END,"
        f"CASE WHEN octet_length(encode(contract_json))<=32768 THEN contract_json END "
        f"FROM {contracts} WHERE dataset_name=? AND contract_version='1'",
        [CONTRACT.name],
    ).fetchall() != [(CONTRACT.fingerprint, CONTRACT.canonical_json())]:
        raise codec.Rejected("FEATURE_SILVER_CONTRACT_DRIFT")
    audit = common.name(conn, "medallion_audit", "schema_versions")
    if conn.execute(f"SELECT version FROM {audit} LIMIT 2").fetchall() != [(1,)]:
        raise codec.Rejected("AUDIT_SCHEMA_DRIFT")


def _context(pins: FeatureBronzePins, raw: bytes) -> bytes:
    if type(raw) is not bytes or not 0 < len(raw) <= codec.MAX_BYTES:
        raise codec.Rejected("FEATURE_SNAPSHOT_BYTE_BOUND")
    context = codec.canonical(dict(version=VERSION, pins=asdict(pins), snapshot_hex=raw.hex()))
    if len(context) > MAX_CONTEXT:
        raise codec.Rejected("FEATURE_CONTEXT_BYTE_BOUND")
    return context


def _derive(context: bytes) -> tuple[FeatureBronzePins, tuple[bytes, ...]]:
    doc = codec.parse(context, MAX_CONTEXT)
    try:
        if set(doc) != {"version", "pins", "snapshot_hex"} or doc["version"] != VERSION:
            raise codec.Rejected("FEATURE_CONTEXT_SCHEMA")
        pins = FeatureBronzePins(**doc["pins"])
        encoded = doc["snapshot_hex"]
        if type(encoded) is not str or not 0 < len(encoded) <= 2 * codec.MAX_BYTES:
            raise codec.Rejected("SNAPSHOT_HEX_BOUND")
        raw = bytes.fromhex(encoded)
        if _context(pins, raw) != context:
            raise codec.Rejected("FEATURE_CONTEXT_REPLAY_MISMATCH")
        doc = codec.replay_snapshot(raw, expected_snapshot_id=pins.snapshot_id)
        if doc["source_label"] != pins.source_label:
            raise codec.Rejected("FEATURE_SOURCE_LABEL_MISMATCH")
        return pins, codec.derive_records(
            raw,
            snapshot_id=pins.snapshot_id,
            capture_event_id=pins.capture_event_id,
            envelope_hash=pins.envelope_hash,
        )
    except codec.Rejected:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise codec.Rejected("MALFORMED_FEATURE_CONTEXT") from None


def observe_feature_snapshot_bronze(bronze: Any, *, pins: FeatureBronzePins) -> bytes:
    pins = _pins(pins)
    first = source.read_feature_snapshot_bronze(bronze, **pins.reader_args())
    fingerprint, raw = source.read_recording_bytes(
        bronze,
        source_label=pins.source_label,
        snapshot_id=pins.snapshot_id,
        capture_event_id=pins.capture_event_id,
        envelope_hash=pins.envelope_hash,
    )
    if fingerprint != pins.recording_fingerprint:
        raise codec.Rejected("FEATURE_BRONZE_RECORDING_CHANGED")
    context = _context(pins, raw)
    _, records = _derive(context)
    second = source.read_feature_snapshot_bronze(bronze, **pins.reader_args())
    if first != second or records != first:
        raise codec.Rejected("FEATURE_BRONZE_FULL_OBSERVATION_DRIFT")
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
    doc = codec.parse(raw, codec.MAX_RECORD)
    fields = doc["stored_fields"]
    scalars = []
    for field, kind in codec.SCHEMA:
        value = fields[field]
        if value is not None:
            if kind == "BIGINT":
                value = int(value)
            elif kind == "DATE":
                value = date.fromisoformat(value)
            elif kind == "TIMESTAMP WITH TIME ZONE":
                value = datetime.fromisoformat(value)
        scalars.append(value)
    return (doc["source_ordinal"], codec.sha(raw), *scalars)


def persist_feature_snapshot_silver(
    bronze: Any,
    target: Any,
    *,
    pins: FeatureBronzePins,
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
        raise codec.Rejected("REVIEWED_FEATURE_SILVER_REQUEST_REQUIRED")
    common._separate(bronze, target)
    _schema(target)
    sets = common.name(target, "silver", "feature_sets")
    records_table = common.name(target, "silver", "feature_observations")
    attempts = common.name(target, "silver", "feature_attempts")
    jobs = common.name(target, "medallion_audit", "jobs")
    for table, field, value in (
        (sets, "scope_id", pins.scope_id),
        (attempts, "scope_id", pins.scope_id),
        (jobs, "scope_ref", "sha256:" + pins.scope_id),
        (records_table, "source_observation_id", pins.capture_event_id),
    ):
        if target.execute(f'SELECT 1 FROM {table} WHERE "{field}"=? LIMIT 1', [value]).fetchone():
            raise codec.Rejected("FEATURE_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION")
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref="sha256:" + pins.scope_id,
        config_hash=codec.sha(codec.canonical([DEFINITION, expected_context_sha256])),
    )
    with ledger.execution(job):
        context = observe_feature_snapshot_bronze(bronze, pins=pins)
        if codec.sha(context) != expected_context_sha256:
            raise codec.Rejected("REVIEWED_FEATURE_CONTEXT_CHANGED")
        _, records = _derive(context)
        if observe_feature_snapshot_bronze(bronze, pins=pins) != context:
            raise codec.Rejected("FEATURE_BRONZE_CONTEXT_DRIFT")
        revision = _revision(context, records)
        at = datetime.now(UTC)
        placeholders = ",".join("?" for _ in range(len(codec.SCHEMA) + 6))
        target.execute("BEGIN TRANSACTION")
        try:
            target.execute(
                f"INSERT INTO {sets} VALUES (?,?,?,?,?,?)",
                [revision, pins.scope_id, context, len(records), job, at],
            )
            for raw in records:
                target.execute(
                    f"INSERT INTO {records_table} VALUES ({placeholders})",
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
    selected = []
    byte_terms = []
    overflow = []
    for field, kind in codec.SCHEMA:
        quoted = '"' + field + '"'
        if kind in ("VARCHAR", "JSON", "DOUBLE"):
            limit = 64 if kind == "DOUBLE" else codec.MAX_CELL
            length = f"octet_length(encode({quoted}))"
            selected.append(f"CASE WHEN {length}<={limit} THEN {quoted} END")
            byte_terms.append(f"coalesce({length},0)")
            overflow.append(f"coalesce({length}>{limit},false)")
        else:
            selected.append(quoted)
    overflow += ["length(record_id)>64", "length(source_observation_id)>64"]
    return ",".join(selected), "+".join(byte_terms), " OR ".join(overflow)


def _recording(conn: Any, revision: str) -> tuple[str, bytes, tuple[bytes, ...]]:
    if not codec.pin(revision):
        raise codec.Rejected("EXACT_FEATURE_SILVER_REVISION_REQUIRED")
    _schema(conn)
    sets = common.name(conn, "silver", "feature_sets")
    records_table = common.name(conn, "silver", "feature_observations")
    attempts = common.name(conn, "silver", "feature_attempts")
    jobs = common.name(conn, "medallion_audit", "jobs")
    events = common.name(conn, "medallion_audit", "job_events")
    selected, scalar_bytes, overflow = _scalar_queries()
    conn.execute("BEGIN TRANSACTION")
    try:
        row = conn.execute(
            f"SELECT CASE WHEN length(scope_id)<=64 THEN scope_id END,"
            f"CASE WHEN octet_length(context)<=? THEN context END,row_count,"
            f"CASE WHEN length(first_job_id)<=128 THEN first_job_id END,recorded_at "
            f"FROM {sets} WHERE revision_id=?",
            [MAX_CONTEXT, revision],
        ).fetchone()
        if row is None or row[0] is None or row[1] is None or row[3] is None:
            raise codec.Rejected("FEATURE_SILVER_SET_MISSING_OR_UNBOUNDED")
        totals = conn.execute(
            f"SELECT count(*),coalesce(sum(octet_length(record_bytes)),0),"
            f"coalesce(max(octet_length(record_bytes)),0),coalesce(sum({scalar_bytes}),0),"
            f"coalesce(bool_or({overflow}),false) FROM {records_table} WHERE revision_id=?",
            [revision],
        ).fetchone()
        if (
            totals is None
            or not 1 <= totals[0] <= codec.MAX_ROWS
            or totals[1] > codec.MAX_RECORDS
            or totals[2] > codec.MAX_RECORD
            or totals[3] > MAX_SCALAR_BYTES
            or totals[4]
        ):
            raise codec.Rejected("FEATURE_SILVER_TRANSFER_BOUND")
        stored = conn.execute(
            f"SELECT ordinal,CASE WHEN length(record_id)<=64 THEN record_id END,{selected},"
            f"CASE WHEN octet_length(record_bytes)<=? THEN record_bytes END,"
            f"CASE WHEN length(source_observation_id)<=64 THEN source_observation_id END,"
            f"recorded_at "
            f"FROM {records_table} WHERE revision_id=? ORDER BY ordinal LIMIT ?",
            [codec.MAX_RECORD, revision, codec.MAX_ROWS + 1],
        ).fetchall()
        links = conn.execute(
            f"SELECT CASE WHEN length(job_id)<=128 THEN job_id END,"
            f"CASE WHEN length(scope_id)<=64 THEN scope_id END,"
            f"CASE WHEN length(revision_id)<=64 THEN revision_id END FROM {attempts} "
            "WHERE scope_id=? OR revision_id=? LIMIT 3",
            [row[0], revision],
        ).fetchall()
        scoped = common._metadata(
            conn,
            f"SELECT CASE WHEN length(job_id)<=128 THEN job_id END,"
            f"CASE WHEN parent_job_id IS NULL THEN NULL ELSE 'PRESENT' END,"
            f"CASE WHEN length(command_name)<=128 THEN command_name END,"
            f"CASE WHEN length(actor_id)<=128 THEN actor_id END,"
            f"CASE WHEN length(code_revision)<=40 THEN code_revision END,"
            f"CASE WHEN length(config_hash)<=64 THEN config_hash END,created_at "
            f"FROM {jobs} WHERE scope_ref=?",
            ["sha256:" + row[0]],
            1,
        )
        history = common._metadata(
            conn,
            f"SELECT event_index,CASE WHEN length(state)<=32 THEN state END,recorded_at,"
            f"CASE WHEN reason_code IS NULL THEN NULL ELSE 'PRESENT' END FROM {events} "
            "WHERE job_id=? ORDER BY event_index",
            [row[3]],
            3,
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    context = bytes(row[1])
    pins, expected = _derive(context)
    if (
        pins.scope_id != row[0]
        or _revision(context, expected) != revision
        or row[2] != len(expected)
        or len(stored) != len(expected)
        or links != [(row[3], row[0], revision)]
    ):
        raise codec.Rejected("FEATURE_SILVER_SET_OR_COVERAGE_MISMATCH")
    width = len(codec.SCHEMA) + 2
    for got, raw in zip(stored, expected, strict=True):
        if (
            got[:width] != _values(raw)
            or got[width] is None
            or bytes(got[width]) != raw
            or got[width + 1 :] != (pins.capture_event_id, row[4])
        ):
            raise codec.Rejected("FEATURE_SILVER_FULL_RECORD_RECOMPUTATION_MISMATCH")
    config = codec.sha(codec.canonical([DEFINITION, codec.sha(context)]))
    if (
        len(scoped) != 1
        or scoped[0][0] != row[3]
        or scoped[0][1] is not None
        or scoped[0][2] != COMMAND
        or not common._actor(scoped[0][3])
        or not common._revision(scoped[0][4])
        or scoped[0][5] != config
        or [(h[0], h[1], h[3]) for h in history]
        != [(1, "PLANNED", None), (2, "RUNNING", None), (3, "SUCCEEDED", None)]
    ):
        raise codec.Rejected("ORIGINAL_FEATURE_SILVER_AUDIT_NOT_VERIFIED")
    for at in [row[4], scoped[0][6], *(h[2] for h in history)]:
        common._clock(at)
    scalar_metadata = []
    for record in stored:
        scalars = []
        for value, (_field, kind) in zip(record[2:width], codec.SCHEMA, strict=True):
            if value is not None and kind == "DATE":
                value = value.isoformat()
            scalars.append(value)
        scalar_metadata.append(
            [*record[:2], scalars, codec.sha(bytes(record[width])), *record[width + 1 :]]
        )
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


def read_feature_snapshot_silver(
    silver: Any, *, revision_id: str, expected_recording_fingerprint: str
) -> tuple[bytes, ...]:
    if not codec.pin(expected_recording_fingerprint):
        raise codec.Rejected("EXACT_FEATURE_SILVER_RECORDING_PIN_REQUIRED")
    common._readonly(silver)
    fingerprint, _context_bytes, records = _recording(silver, revision_id)
    if fingerprint != expected_recording_fingerprint:
        raise codec.Rejected("FEATURE_SILVER_RECORDING_FINGERPRINT_CHANGED")
    return records


def revalidate_feature_snapshot_silver(
    bronze: Any, silver: Any, *, revision_id: str, expected_recording_fingerprint: str
) -> tuple[bytes, ...]:
    common._separate(bronze, silver)
    args = dict(
        revision_id=revision_id, expected_recording_fingerprint=expected_recording_fingerprint
    )
    first = read_feature_snapshot_silver(silver, **args)
    fingerprint, frozen, _records = _recording(silver, revision_id)
    if fingerprint != expected_recording_fingerprint:
        raise codec.Rejected("FEATURE_SILVER_RECORDING_FINGERPRINT_CHANGED")
    pins, _records = _derive(frozen)
    for _ in range(2):
        if observe_feature_snapshot_bronze(bronze, pins=pins) != frozen:
            raise codec.Rejected("CURRENT_FEATURE_BRONZE_CONTEXT_CHANGED")
    second = read_feature_snapshot_silver(silver, **args)
    if first != second:
        raise codec.Rejected("FEATURE_SILVER_CHANGED_DURING_REVALIDATION")
    return second
