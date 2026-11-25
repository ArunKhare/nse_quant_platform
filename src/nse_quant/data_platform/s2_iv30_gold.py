"""Audited S2 India VIX live-IV30 Gold candidates; never publication or eligibility.

The writer freshly derives the candidate from retained Bronze/Silver and the
audited S2 materialization. Retrieval is exact-pin, as-of and audit-aware.
No publication, decision-loop wiring, model-suitability claim or trading authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nse_quant.data_platform import s2_iv30_feature_reader as feature_reader
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy

VERSION = "s2-india-vix-iv30-gold-candidates@1"
FEATURE_VERSION = "s2-observational-iv30-features@1"
COMMAND = "build.s2_india_vix_iv30_candidate@1"
SCHEMA_VERSION = 1
MAX_FEATURE_BYTES = 6 * 1024 * 1024
MAX_HISTORY = 1000
TABLE = "s2_iv30_candidates"
DEFINITIONS = "s2_iv30_candidate_definitions"
CONTRACT = DatasetContract(
    "gold.s2_iv30_candidates",
    "1",
    Layer.GOLD,
    WritePolicy.VERSIONED_BUILDS,
    ("build_id",),
    ("build_id", "event_ts", "published_at", "feature_version"),
    "s2_india_vix_iv30_gold_candidates",
)
DEFINITION = {
    "version": VERSION,
    "feature_version": FEATURE_VERSION,
    "source": "india_vix",
    "mode": "observation",
    "publication_asserted": False,
    "decision_eligibility_asserted": False,
}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pin(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("S2_GOLD_AWARE_TIME_REQUIRED")
    return parsed.astimezone(UTC)


def _path(conn: Any, *, readonly: bool | None = None) -> str:
    rows = conn.execute(
        "SELECT path,readonly FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall()
    if len(rows) != 1 or not rows[0][0]:
        raise ValueError("S2_GOLD_FILE_BACKED_DATABASE_REQUIRED")
    if readonly is not None and rows[0][1] is not readonly:
        raise ValueError("S2_GOLD_READONLY_ROLE_MISMATCH")
    return str(rows[0][0])


def _separate(sources: tuple[Any, ...], gold: Any) -> None:
    target = Path(_path(gold, readonly=False)).resolve()
    source_paths = [Path(_path(source, readonly=True)).resolve() for source in sources]
    if len(set(source_paths)) != len(source_paths) or target in source_paths:
        raise ValueError("S2_GOLD_SEPARATE_READONLY_SOURCES_REQUIRED")


def _actor(actor_id: str, code_revision: str) -> None:
    if (
        type(actor_id) is not str
        or not actor_id.strip()
        or len(actor_id.encode()) > 128
        or type(code_revision) is not str
        or re.fullmatch(r"[a-f0-9]{40}", code_revision) is None
    ):
        raise ValueError("S2_GOLD_ACTOR_AND_40_CHAR_CODE_REVISION_REQUIRED")


def _name(conn: Any, table: str, schema: str = "gold") -> str:
    catalog = conn.execute("SELECT current_database()").fetchone()[0]
    return ".".join(
        '"' + part.replace('"', '""') + '"' for part in (catalog, schema, table)
    )


def _validate_feature(raw: bytes, *, as_of: str) -> dict[str, Any]:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_FEATURE_BYTES:
        raise ValueError("S2_GOLD_FEATURE_BYTE_BOUND")
    try:
        feature = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("S2_GOLD_FEATURE_MALFORMED") from exc
    if type(feature) is not dict or canonical(feature) != raw:
        raise ValueError("S2_GOLD_FEATURE_NOT_CANONICAL")
    if (
        feature.get("version") != FEATURE_VERSION
        or feature.get("feature_kind") != "live_iv30_observation"
        or feature.get("iv30_source") != "india_vix"
        or feature.get("mode") != "observation"
        or feature.get("publication_asserted") is not False
        or feature.get("decision_eligibility_asserted") is not False
        or feature.get("model_suitability_verified") is not False
        or feature.get("vrp_gate_passed") is not False
        or feature.get("quality_state") != "valid_observation"
    ):
        raise ValueError("S2_GOLD_FEATURE_PROFILE_OR_AUTHORITY_MISMATCH")
    value = feature.get("iv30")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError("S2_GOLD_FINITE_POSITIVE_IV30_REQUIRED")
    source_time = _instant(feature.get("source_time", ""))
    received_at = _instant(feature.get("received_at", ""))
    cutoff = _instant(as_of)
    feature_time = _instant(feature.get("as_of", ""))
    if not source_time <= received_at <= feature_time <= cutoff:
        raise ValueError("S2_GOLD_FUTURE_OR_UNORDERED_FEATURE_DEPENDENCY")
    age = feature.get("age_seconds")
    age_limit = feature.get("max_age_seconds")
    percent = feature.get("value_percent")
    token = feature.get("instrument_token")
    revisions = feature.get("source_revisions")
    if (
        isinstance(age, bool)
        or not isinstance(age, (int, float))
        or not math.isfinite(age)
        or age < 0
        or isinstance(age_limit, bool)
        or not isinstance(age_limit, (int, float))
        or not math.isfinite(age_limit)
        or age_limit <= 0
        or age > age_limit
        or not math.isclose(float(age), (feature_time - source_time).total_seconds(), rel_tol=1e-9, abs_tol=1e-6)
        or isinstance(percent, bool)
        or not isinstance(percent, (int, float))
        or not math.isfinite(percent)
        or not math.isclose(float(value) * 100, float(percent), rel_tol=1e-12, abs_tol=1e-12)
        or type(token) is not int
        or token <= 0
        or type(revisions) is not list
        or not revisions
        or any(not pin(item) for item in revisions)
        or feature.get("selected_revision_id") not in revisions
        or not pin(feature.get("raw_payload_sha256"))
        or not pin(feature.get("instrument_reference_sha256"))
    ):
        raise ValueError("S2_GOLD_LIVE_OBSERVATION_CONTRACT_MISMATCH")
    provenance = feature.get("provenance")
    if (
        type(provenance) is not dict
        or not pin(provenance.get("observation_id"))
        or not pin(provenance.get("materialization_sha256"))
        or not pin(provenance.get("revision_id"))
    ):
        raise ValueError("S2_GOLD_EXACT_S2_PROVENANCE_REQUIRED")
    return feature


def initialize(gold: Any, *, actor_id: str, code_revision: str) -> None:
    _actor(actor_id, code_revision)
    _path(gold, readonly=False)
    inventory = gold.execute(
        "SELECT table_schema,table_name FROM information_schema.tables "
        "WHERE table_catalog=current_database() LIMIT 20"
    ).fetchall()
    if inventory:
        raise ValueError("S2_GOLD_EMPTY_DEDICATED_STORE_REQUIRED")
    ledger = AuditLedger(gold)
    ledger.initialize()
    gold.execute("BEGIN TRANSACTION")
    try:
        gold.execute("CREATE SCHEMA gold")
        gold.execute(
            f"CREATE TABLE {_name(gold, 'schema_versions')} "
            "(version INTEGER PRIMARY KEY)"
        )
        gold.execute(f"INSERT INTO {_name(gold, 'schema_versions')} VALUES (?)", [SCHEMA_VERSION])
        gold.execute(
            f"CREATE TABLE {_name(gold, DEFINITIONS)} ("
            "version INTEGER PRIMARY KEY, definition BLOB NOT NULL, "
            "definition_sha256 VARCHAR NOT NULL, recorded_at TIMESTAMPTZ NOT NULL, "
            "first_job_id VARCHAR NOT NULL)"
        )
        gold.execute(
            f"CREATE TABLE {_name(gold, TABLE)} ("
            "build_id VARCHAR PRIMARY KEY, input_revision_id VARCHAR NOT NULL, "
            "feature_version VARCHAR NOT NULL, status VARCHAR NOT NULL, "
            "reason_code VARCHAR NOT NULL, feature_sha256 VARCHAR NOT NULL, "
            "feature_json BLOB NOT NULL, event_ts TIMESTAMPTZ NOT NULL, "
            "published_at TIMESTAMPTZ, recorded_at TIMESTAMPTZ NOT NULL, "
            "first_job_id VARCHAR NOT NULL, UNIQUE(input_revision_id, build_id))"
        )
        gold.execute("COMMIT")
    except BaseException:
        gold.execute("ROLLBACK")
        raise
    ledger.register_contract(CONTRACT)


def _verify_store(gold: Any, *, require_definition: bool = False) -> None:
    if gold.execute(f"SELECT version FROM {_name(gold, 'schema_versions')} LIMIT 2").fetchall() != [
        (SCHEMA_VERSION,)
    ]:
        raise ValueError("S2_GOLD_SCHEMA_VERSION_MISMATCH")
    definition = gold.execute(
        f"SELECT definition,definition_sha256 FROM {_name(gold, DEFINITIONS)} LIMIT 2"
    ).fetchall()
    expected = canonical(DEFINITION)
    if len(definition) > 1 or (definition and definition != [(expected, sha(expected))]):
        raise ValueError("S2_GOLD_DEFINITION_DRIFT")
    if require_definition and definition != [(expected, sha(expected))]:
        raise ValueError("S2_GOLD_DEFINITION_REQUIRED")
    contract = gold.execute(
        "SELECT fingerprint,contract_json FROM medallion_audit.dataset_contracts "
        "WHERE dataset_name=? AND contract_version=? LIMIT 2",
        [CONTRACT.name, CONTRACT.version],
    ).fetchall()
    if contract != [(CONTRACT.fingerprint, CONTRACT.canonical_json())]:
        raise ValueError("S2_GOLD_CONTRACT_DRIFT")


def persist_live_candidate(
    bronze: Any,
    vix_silver: Any,
    materializations: Any,
    gold: Any,
    *,
    observation_id: str,
    expected_sha256: str,
    as_of: str,
    actor_id: str,
    code_revision: str,
    max_age_seconds: float = 300,
    initialize_store: bool = False,
) -> dict[str, Any]:
    """Freshly compute from exact native pins and append a non-published Gold candidate."""
    _actor(actor_id, code_revision)
    if not pin(observation_id) or not pin(expected_sha256):
        raise ValueError("S2_GOLD_EXACT_MATERIALIZATION_PINS_REQUIRED")
    cutoff = _instant(as_of)
    sources = (bronze, vix_silver, materializations)
    _separate(sources, gold)
    feature_raw = feature_reader.read_live_feature(
        materializations,
        bronze,
        vix_silver,
        observation_id=observation_id,
        expected_sha256=expected_sha256,
        as_of=cutoff.isoformat(),
        max_age_seconds=max_age_seconds,
    )
    feature = _validate_feature(feature_raw, as_of=cutoff.isoformat())
    if feature["provenance"]["observation_id"] != observation_id:
        raise ValueError("S2_GOLD_OBSERVATION_PIN_MISMATCH")
    if initialize_store:
        initialize(gold, actor_id=actor_id, code_revision=code_revision)
    _verify_store(gold)
    feature_hash = sha(feature_raw)
    input_revision_id = sha(
        canonical(
            [
                VERSION,
                observation_id,
                expected_sha256,
                feature["provenance"]["revision_id"],
                feature_hash,
            ]
        )
    )
    build_id = sha(canonical([VERSION, input_revision_id, feature_hash]))
    event_ts = _instant(feature["source_time"])
    ledger = AuditLedger(gold)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        scope_ref="sha256:" + input_revision_id,
        code_revision=code_revision,
        config_hash=sha(canonical([VERSION, FEATURE_VERSION, sha(canonical(DEFINITION))])),
    )
    table = _name(gold, TABLE)
    definitions = _name(gold, DEFINITIONS)
    inserted = False
    with ledger.execution(job):
        gold.execute("BEGIN TRANSACTION")
        try:
            definition = gold.execute(
                f"SELECT definition,definition_sha256 FROM {definitions} LIMIT 2"
            ).fetchall()
            expected_definition = (canonical(DEFINITION), sha(canonical(DEFINITION)))
            if not definition:
                gold.execute(
                    f"INSERT INTO {definitions} VALUES (1,?,?,?,?)",
                    [*expected_definition, datetime.now(UTC), job],
                )
            elif definition != [expected_definition]:
                raise ValueError("S2_GOLD_DEFINITION_VERSION_CONTENT_MISMATCH")
            previous = gold.execute(
                f"SELECT input_revision_id,feature_version,status,reason_code,feature_sha256,"
                f"feature_json,event_ts,published_at FROM {table} WHERE build_id=? LIMIT 2",
                [build_id],
            ).fetchall()
            expected_row = (
                input_revision_id,
                FEATURE_VERSION,
                "candidate",
                "OBSERVATIONAL_IV30_CANDIDATE",
                feature_hash,
                feature_raw,
                event_ts,
                None,
            )
            if previous:
                if previous != [expected_row]:
                    raise ValueError("S2_GOLD_BUILD_CONTENT_MISMATCH")
            else:
                count = gold.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE input_revision_id=?",
                    [input_revision_id],
                ).fetchone()[0]
                if count >= MAX_HISTORY:
                    raise ValueError("S2_GOLD_BUILD_HISTORY_LIMIT")
                gold.execute(
                    f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    [
                        build_id,
                        input_revision_id,
                        FEATURE_VERSION,
                        "candidate",
                        "OBSERVATIONAL_IV30_CANDIDATE",
                        feature_hash,
                        feature_raw,
                        event_ts,
                        None,
                        datetime.now(UTC),
                        job,
                    ],
                )
                inserted = True
            gold.execute("COMMIT")
        except BaseException:
            gold.execute("ROLLBACK")
            raise
    return {
        "build_id": build_id,
        "input_revision_id": input_revision_id,
        "job_id": job,
        "inserted": inserted,
        "status": "candidate",
        "published": False,
        "decision_eligibility_asserted": False,
    }


def retrieve_candidate(
    gold: Any,
    *,
    build_id: str,
    as_of: str,
) -> dict[str, Any]:
    """Retrieve an exact candidate only after its original audit succeeded."""
    if not pin(build_id):
        raise ValueError("S2_GOLD_EXACT_BUILD_PIN_REQUIRED")
    cutoff = _instant(as_of)
    _path(gold, readonly=True)
    _verify_store(gold, require_definition=True)
    table = _name(gold, TABLE)
    row = gold.execute(
        f"SELECT input_revision_id,feature_version,status,reason_code,feature_sha256,"
        f"feature_json,event_ts,published_at,recorded_at,first_job_id "
        f"FROM {table} WHERE build_id=? LIMIT 2",
        [build_id],
    ).fetchall()
    if len(row) != 1:
        return {
            "status": "CANDIDATE_NOT_AVAILABLE",
            "build_id": build_id,
            "decision_eligibility_asserted": False,
        }
    record = row[0]
    if record[8] > cutoff or record[6] > cutoff:
        raise ValueError("S2_GOLD_CANDIDATE_NOT_YET_AVAILABLE")
    raw = bytes(record[5])
    if sha(raw) != record[4]:
        raise ValueError("S2_GOLD_FEATURE_HASH_MISMATCH")
    feature = _validate_feature(raw, as_of=cutoff.isoformat())
    if (
        record[1:4] != (FEATURE_VERSION, "candidate", "OBSERVATIONAL_IV30_CANDIDATE")
        or record[7] is not None
        or feature["provenance"]["revision_id"] is None
    ):
        raise ValueError("S2_GOLD_CANDIDATE_CONTRACT_MISMATCH")
    events = _name(gold, "job_events", "medallion_audit")
    audit = gold.execute(
        f"SELECT event_index,state,reason_code FROM {events} "
        "WHERE job_id=? ORDER BY event_index LIMIT 4",
        [record[9]],
    ).fetchall()
    if [(item[0], item[1], item[2]) for item in audit] != [
        (1, "PLANNED", None),
        (2, "RUNNING", None),
        (3, "SUCCEEDED", None),
    ]:
        raise ValueError("S2_GOLD_SUCCESSFUL_ORIGINAL_AUDIT_REQUIRED")
    return {
        "status": "CANDIDATE_RETRIEVED_NOT_PUBLISHED",
        "build_id": build_id,
        "input_revision_id": record[0],
        "feature_sha256": record[4],
        "feature": feature,
        "recorded_at": record[8].isoformat(),
        "event_ts": record[6].isoformat(),
        "published_at": None,
        "publication_asserted": False,
        "decision_eligibility_asserted": False,
        "model_suitability_verified": False,
    }
