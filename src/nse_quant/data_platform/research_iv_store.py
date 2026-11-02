"""Audited immutable research-IV Gold records; archive integrity is not publication."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.research_iv_record import (
    MAX_RESULT_BYTES,
    MAX_TERMS_BYTES,
    build_id,
    canonical,
    checked_json,
    input_id,
    pin,
    sha,
    validate_prior_links,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.research_option_model import ScenarioTerms

VERSION = "audited-research-iv-builds@1"
FEATURE_VERSION = "research-native-bsm-iv-build@1"
COMMAND = "build.research_iv_scenario@1"
MAX_BUILDS = 256
MAX_JOBS = 1000


class IvArchiveReviewRequired(ValueError):
    """Scoped history/audit is not complete; never accept an older good result."""


@dataclass(frozen=True)
class ResearchIvArchive:
    version: str
    build_id: str
    input_id: str
    status: str
    reason_codes: tuple[str, ...]
    retained_head_build_id: str
    recorded_result_status: str
    result_json: str
    terms_json: str
    evidence_fingerprint: str
    archived_recording_verified: bool = True
    current_source_checked: bool = False
    archived_pin_is_head: bool = False
    publication_asserted: bool = False
    historical_validity_asserted: bool = False
    decision_eligibility_asserted: bool = False
    canonical_contract_id: None = None


def _name(conn: Any, schema: str, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise ValueError("RESEARCH_IV_CATALOG_UNAVAILABLE")
    return ".".join('"' + str(x).replace('"', '""') + '"' for x in (row[0], schema, table))


def _paths(conn: Any) -> tuple[Path, ...]:
    return tuple(Path(row[2]) for row in conn.execute("PRAGMA database_list").fetchall() if row[2])


def _owned(conn: Any) -> None:
    catalog = conn.execute("SELECT current_database()").fetchone()[0]
    if not any(
        row[1] == catalog and row[2] for row in conn.execute("PRAGMA database_list").fetchall()
    ):
        raise ValueError("FILE_BACKED_RESEARCH_IV_TARGET_REQUIRED")
    allowed = {
        ("gold", "research_iv_schema_versions"),
        ("gold", "research_iv_definitions"),
        ("gold", "research_iv_builds"),
        ("gold", "research_iv_attempts"),
        ("medallion_audit", "schema_versions"),
        ("medallion_audit", "dataset_contracts"),
        ("medallion_audit", "jobs"),
        ("medallion_audit", "job_events"),
    }
    rows = conn.execute(
        "SELECT table_schema,table_name FROM information_schema.tables "
        "WHERE table_catalog=current_database()"
    ).fetchall()
    if any(tuple(row) not in allowed for row in rows):
        raise ValueError("DEDICATED_RESEARCH_IV_TARGET_REQUIRED")


def _contract() -> Any:
    from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy

    return DatasetContract(
        "gold.research_iv_builds",
        "1",
        Layer.GOLD,
        WritePolicy.VERSIONED_BUILDS,
        ("build_id",),
        ("build_id", "event_ts", "published_at", "feature_version"),
        "native_research_option_analytics",
    )


def _definition() -> str:
    from nse_quant.data_platform import native_research_option as native
    from nse_quant.data_platform import research_option_model as model

    if (
        native.VERSION != "native-gold-research-iv-candidate@1"
        or model.VERSION != "research-european-bsm-iv@1"
    ):
        raise ValueError("UNSUPPORTED_RESEARCH_IV_STORE_DEPENDENCY_VERSION")
    return canonical(
        [
            VERSION,
            FEATURE_VERSION,
            native.VERSION,
            model.VERSION,
            model.SIGMA_LOW,
            model.SIGMA_HIGH,
            model.PRICE_ATOL,
            model.PRICE_RTOL,
            model.SOLVER_XTOL,
            model.SOLVER_RTOL,
            model.MAX_ITERATIONS,
            "research-only-original-source-times-no-publication@1",
        ]
    )


def _initialize(conn: Any) -> None:
    from nse_quant.data_platform.audit import AuditLedger

    _owned(conn)
    AuditLedger(conn).initialize()
    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute('CREATE SCHEMA IF NOT EXISTS "gold"')
        table = _name(conn, "gold", "research_iv_schema_versions")
        conn.execute(f"CREATE TABLE IF NOT EXISTS {table} (version INTEGER PRIMARY KEY)")
        rows = conn.execute(f"SELECT version FROM {table} LIMIT 2").fetchall()
        if rows and rows != [(1,)]:
            raise ValueError("RESEARCH_IV_SCHEMA_NOT_SUPPORTED")
        definitions = _name(conn, "gold", "research_iv_definitions")
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {definitions} ("
            "feature_version VARCHAR PRIMARY KEY,definition_json VARCHAR NOT NULL,"
            "definition_hash VARCHAR NOT NULL,first_job_id VARCHAR NOT NULL,"
            "recorded_at TIMESTAMPTZ NOT NULL)"
        )
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {_name(conn, 'gold', 'research_iv_builds')} ("
            "build_id VARCHAR PRIMARY KEY,input_id VARCHAR NOT NULL,"
            "ordinal INTEGER NOT NULL,"
            "feature_version VARCHAR NOT NULL,option_build_id VARCHAR NOT NULL,"
            "spot_build_id VARCHAR NOT NULL,terms_pin VARCHAR NOT NULL,"
            "definition_hash VARCHAR NOT NULL,terms_json VARCHAR NOT NULL,"
            "result_json VARCHAR NOT NULL,prior_ids_json VARCHAR NOT NULL,"
            "first_job_id VARCHAR NOT NULL,recorded_at TIMESTAMPTZ NOT NULL,"
            "event_ts TIMESTAMPTZ,published_at TIMESTAMPTZ,UNIQUE(input_id,ordinal))"
        )
        attempts = _name(conn, "gold", "research_iv_attempts")
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {attempts} ("
            "job_id VARCHAR PRIMARY KEY,input_id VARCHAR NOT NULL,"
            "build_id VARCHAR NOT NULL)"
        )
        if not rows:
            if any(
                conn.execute(f"SELECT 1 FROM {_name(conn, 'gold', name)} LIMIT 1").fetchone()
                for name in (
                    "research_iv_builds",
                    "research_iv_definitions",
                    "research_iv_attempts",
                )
            ):
                raise ValueError("RESEARCH_IV_PARTIAL_SCHEMA_NOT_ADOPTABLE")
            conn.execute(f"INSERT INTO {table} VALUES (1)")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def _instant(value: object) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise IvArchiveReviewRequired("RESEARCH_IV_AWARE_RECORD_CLOCK_REQUIRED")
    return value.astimezone(UTC).isoformat()


def _scope(
    conn: Any, group: str, definition_hash: str, active_job: str | None = None
) -> tuple[list[tuple[Any, ...]], str]:
    builds = _name(conn, "gold", "research_iv_builds")
    rows = conn.execute(
        f"SELECT build_id,input_id,ordinal,feature_version,option_build_id,spot_build_id,terms_pin,"
        f"definition_hash,CASE WHEN octet_length(encode(terms_json))<=? THEN terms_json END,"
        f"CASE WHEN octet_length(encode(result_json))<=? THEN result_json END,"
        f"CASE WHEN octet_length(encode(prior_ids_json))<=32768 THEN prior_ids_json END,"
        f"first_job_id,recorded_at,event_ts,published_at FROM {builds} "
        "WHERE input_id=? ORDER BY ordinal LIMIT ?",
        [MAX_TERMS_BYTES, MAX_RESULT_BYTES, group, MAX_BUILDS + 1],
    ).fetchall()
    attempts = conn.execute(
        f"SELECT job_id,build_id FROM {_name(conn, 'gold', 'research_iv_attempts')} "
        "WHERE input_id=? ORDER BY job_id LIMIT ?",
        [group, MAX_JOBS + 1],
    ).fetchall()
    jobs = conn.execute(
        f"SELECT job_id,parent_job_id,command_name,config_hash,created_at,actor_id,code_revision "
        f"FROM {_name(conn, 'medallion_audit', 'jobs')} WHERE scope_ref=? "
        "ORDER BY job_id LIMIT ?",
        [group, MAX_JOBS + 1],
    ).fetchall()
    if len(rows) > MAX_BUILDS or len(attempts) > MAX_JOBS or len(jobs) > MAX_JOBS:
        raise IvArchiveReviewRequired("RESEARCH_IV_SCOPED_HISTORY_LIMIT")
    ids: list[str] = []
    origins: dict[str, str] = {}
    normalized_rows: list[object] = []
    for index, row in enumerate(rows, 1):
        key, scope, ordinal, feature, option, spot, terms_pin, definition, terms, result = row[:10]
        if (
            scope != group
            or type(ordinal) is not int
            or ordinal != index
            or feature != FEATURE_VERSION
            or definition != definition_hash
            or input_id(option, spot, terms_pin, definition) != group
            or build_id(group, result) != key
            or key in ids
            or any(x is not None for x in row[13:])
        ):
            raise IvArchiveReviewRequired("RESEARCH_IV_RECORD_IDENTITY_OR_TEMPORAL_MISMATCH")
        terms_value = checked_json(terms, MAX_TERMS_BYTES)
        if sha(canonical(["research-european-bsm-iv@1", terms_value]).encode()) != terms_pin:
            raise IvArchiveReviewRequired("RESEARCH_IV_STORED_TERMS_PIN_MISMATCH")
        result_value = checked_json(result)
        if (
            result_value.get("option_build_id"),
            result_value.get("spot_build_id"),
            result_value.get("scenario_terms_sha256"),
        ) != (option, spot, terms_pin) or (
            result_value.get("version") != "native-gold-research-iv-candidate@1"
            or result_value.get("status") not in ("research_iv_candidate", "review_required")
            or any(
                result_value.get(flag) is not False
                for flag in (
                    "scenario_terms_authoritative",
                    "option_underlying_identity_binding_verified",
                    "availability_evidence_verified",
                    "historical_validity_asserted",
                    "publication_asserted",
                    "decision_eligibility_asserted",
                    "atomic_cross_database_snapshot_asserted",
                )
            )
            or result_value.get("canonical_contract_id") is not None
        ):
            raise IvArchiveReviewRequired("RESEARCH_IV_RECORDED_CANDIDATE_CONTRACT_MISMATCH")
        validate_prior_links(row[10], tuple(ids))
        ids.append(key)
        origins[key] = row[11]
        normalized_rows.append([*row[:12], _instant(row[12]), None, None])
    links = dict(attempts)
    if len(links) != len(attempts) or any(key not in origins for key in links.values()):
        raise IvArchiveReviewRequired("RESEARCH_IV_ATTEMPT_LINK_INVALID")
    audit: list[object] = []
    for job, parent, command, config, created, actor, revision in jobs:
        events = conn.execute(
            f"SELECT event_index,state,recorded_at,reason_code "
            f"FROM {_name(conn, 'medallion_audit', 'job_events')} WHERE job_id=? "
            "ORDER BY event_index LIMIT 7",
            [job],
        ).fetchall()
        expected = (
            ("PLANNED", "RUNNING") if job == active_job else ("PLANNED", "RUNNING", "SUCCEEDED")
        )
        if (
            parent is not None
            or command != COMMAND
            or config != definition_hash
            or any(type(x[0]) is not int for x in events)
            or tuple(x[0] for x in events) != tuple(range(1, len(expected) + 1))
            or tuple(x[1] for x in events) != expected
            or any(x[3] is not None for x in events)
            or any(not isinstance(x, str) or not 0 < len(x) <= 256 for x in (actor, revision))
            or job != active_job
            and job not in links
        ):
            raise IvArchiveReviewRequired("RESEARCH_IV_FAILED_OR_INCOMPLETE_AUDIT_OBLIGATION")
        audit.append(
            [
                job,
                parent,
                command,
                config,
                _instant(created),
                actor,
                revision,
                [[x[0], x[1], _instant(x[2]), x[3]] for x in events],
            ]
        )
    job_ids = {row[0] for row in jobs}
    if (
        active_job is not None
        and active_job not in job_ids
        or any(job not in job_ids for job in links)
        or any(job not in links or links[job] != key for key, job in origins.items())
    ):
        raise IvArchiveReviewRequired("RESEARCH_IV_ORIGIN_NOT_SUCCESSFULLY_LINKED")
    return rows, sha(canonical([VERSION, group, normalized_rows, attempts, audit]).encode())


def _global(
    conn: Any,
    definition: str,
    *,
    allow_empty: bool = False,
    active_job: str | None = None,
    active_scope: str | None = None,
) -> str | None:
    _owned(conn)
    for schema, table in (
        ("gold", "research_iv_schema_versions"),
        ("medallion_audit", "schema_versions"),
    ):
        if conn.execute(f"SELECT version FROM {_name(conn, schema, table)} LIMIT 2").fetchall() != [
            (1,)
        ]:
            raise IvArchiveReviewRequired("RESEARCH_IV_SCHEMA_NOT_SUPPORTED")
    definitions = conn.execute(
        f"SELECT feature_version,CASE WHEN octet_length(encode(definition_json))<=32768 "
        f"THEN definition_json END,definition_hash,first_job_id,recorded_at "
        f"FROM {_name(conn, 'gold', 'research_iv_definitions')} LIMIT 2"
    ).fetchall()
    contract = _contract()
    registered = conn.execute(
        f"SELECT fingerprint,CASE WHEN octet_length(encode(contract_json))<=32768 "
        f"THEN contract_json END,registered_at "
        f"FROM {_name(conn, 'medallion_audit', 'dataset_contracts')} "
        "WHERE dataset_name=? AND contract_version='1' LIMIT 2",
        [contract.name],
    ).fetchall()
    if not definitions and allow_empty:
        nonempty = any(
            conn.execute(f"SELECT 1 FROM {_name(conn, 'gold', table)} LIMIT 1").fetchone()
            for table in ("research_iv_builds", "research_iv_attempts")
        )
        if registered or nonempty:
            raise IvArchiveReviewRequired("RESEARCH_IV_ORPHAN_DOMAIN_NOT_ADOPTABLE")
        return None
    if (
        len(definitions) != 1
        or definitions[0][:3] != (FEATURE_VERSION, definition, sha(definition.encode()))
        or len(registered) != 1
        or registered[0][:2] != (contract.fingerprint, contract.canonical_json())
    ):
        raise IvArchiveReviewRequired("RESEARCH_IV_DEFINITION_OR_CONTRACT_MISMATCH")
    _instant(definitions[0][4])
    _instant(registered[0][2])
    origin_job = definitions[0][3]
    origin_links = conn.execute(
        f"SELECT input_id,build_id FROM {_name(conn, 'gold', 'research_iv_attempts')} "
        "WHERE job_id=? LIMIT 2",
        [origin_job],
    ).fetchall()
    if len(origin_links) != 1:
        raise IvArchiveReviewRequired("RESEARCH_IV_DEFINITION_ORIGIN_MISSING")
    # Verify definition origin in ITS OWN scope, not the requested build's scope.
    origin_scope = origin_links[0][0]
    origin_rows, origin_fingerprint = _scope(
        conn,
        origin_scope,
        sha(definition.encode()),
        active_job if origin_scope == active_scope else None,
    )
    if not any(row[0] == origin_links[0][1] and row[11] == origin_job for row in origin_rows):
        raise IvArchiveReviewRequired("RESEARCH_IV_DEFINITION_ORIGIN_NOT_OWN_RECORDING")
    return sha(
        canonical(
            [
                VERSION,
                definition,
                definitions[0][:4],
                _instant(definitions[0][4]),
                registered[0][:2],
                _instant(registered[0][2]),
                origin_links,
                origin_fingerprint,
            ]
        ).encode()
    )


def persist_research_iv_build(
    bronze: Any,
    frame_silver: Any,
    reference_silver: Any,
    assessments: Any,
    source_gold: Any,
    target: Any,
    *,
    option_build_id: str,
    spot_build_id: str,
    terms: ScenarioTerms,
    expected_scenario_terms_sha256: str,
    actor_id: str,
    code_revision: str,
    initialize: bool = False,
) -> dict[str, object]:
    from nse_quant.data_platform import native_research_option as native
    from nse_quant.data_platform.audit import AuditLedger
    from nse_quant.data_platform.research_option_model import ScenarioTerms, scenario_terms_sha256

    if type(initialize) is not bool or any(
        not isinstance(x, str)
        or not 0 < len(x) <= 256
        or x != x.strip()
        or any(ord(c) < 32 for c in x)
        for x in (actor_id, code_revision)
    ):
        raise ValueError("BOUNDED_RESEARCH_IV_EXECUTION_IDENTIFIERS_REQUIRED")
    if type(terms) is not ScenarioTerms:
        raise TypeError("TYPED_RESEARCH_IV_TERMS_REQUIRED")
    checked = ScenarioTerms(**asdict(terms))
    terms_pin = scenario_terms_sha256(checked)
    if expected_scenario_terms_sha256 != terms_pin:
        raise ValueError("EXACT_RESEARCH_IV_TERMS_PIN_MISMATCH")
    definition = _definition()
    definition_hash = sha(definition.encode())
    group = input_id(option_build_id, spot_build_id, terms_pin, definition_hash)
    if len(definition.encode()) > 32768:
        raise ValueError("RESEARCH_IV_DEFINITION_LIMIT")
    _owned(target)
    output_paths = _paths(target)
    for source in (bronze, frame_silver, reference_silver, assessments, source_gold):
        if source is target or any(
            a == b or a.samefile(b) for a in output_paths for b in _paths(source)
        ):
            raise ValueError("SEPARATE_RESEARCH_IV_OUTPUT_REQUIRED")
    if initialize:
        _initialize(target)
    target.execute("BEGIN TRANSACTION")
    try:
        _global(target, definition, allow_empty=True)
        _scope(target, group, definition_hash)
        target.execute("COMMIT")
    except BaseException:
        target.execute("ROLLBACK")
        raise
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref=group,
        config_hash=definition_hash,
    )
    with ledger.execution(job):
        candidate = native.build_native_research_iv_candidate(
            bronze,
            frame_silver,
            reference_silver,
            assessments,
            source_gold,
            option_build_id=option_build_id,
            spot_build_id=spot_build_id,
            terms=checked,
            expected_scenario_terms_sha256=terms_pin,
        )
        if (
            type(candidate) is not native.NativeResearchIvCandidate
            or candidate.version != native.VERSION
            or (candidate.option_build_id, candidate.spot_build_id, candidate.scenario_terms_sha256)
            != (option_build_id, spot_build_id, terms_pin)
            or candidate.status not in ("research_iv_candidate", "review_required")
            or candidate.canonical_contract_id is not None
            or (
                candidate.status == "research_iv_candidate"
                and (
                    candidate.native_price_inputs_rechecked is not True
                    or not pin(candidate.evidence_fingerprint)
                    or candidate.calculation is None
                    or candidate.calculation.status != "computed_research_scenario"
                )
            )
            or any(
                flag is not False
                for flag in (
                    candidate.scenario_terms_authoritative,
                    candidate.option_underlying_identity_binding_verified,
                    candidate.availability_evidence_verified,
                    candidate.historical_validity_asserted,
                    candidate.publication_asserted,
                    candidate.decision_eligibility_asserted,
                    candidate.atomic_cross_database_snapshot_asserted,
                )
            )
        ):
            raise ValueError("RESEARCH_IV_NATIVE_CANDIDATE_CONTRACT_MISMATCH")
        result_json, terms_json = canonical(asdict(candidate)), canonical(asdict(checked))
        checked_json(terms_json, MAX_TERMS_BYTES)
        key = build_id(group, result_json)
        target.execute("BEGIN TRANSACTION")
        try:
            _global(target, definition, allow_empty=True, active_job=job, active_scope=group)
            rows, _ = _scope(target, group, definition_hash, active_job=job)
            contract = _contract()
            existing = target.execute(
                f"SELECT fingerprint,contract_json FROM "
                f"{_name(target, 'medallion_audit', 'dataset_contracts')} "
                "WHERE dataset_name=? AND contract_version='1' LIMIT 2",
                [contract.name],
            ).fetchall()
            if existing and existing != [(contract.fingerprint, contract.canonical_json())]:
                raise ValueError("RESEARCH_IV_CONTRACT_VERSION_CONTENT_MISMATCH")
            ledger.register_contract(contract)
            table = _name(target, "gold", "research_iv_definitions")
            definitions = target.execute(
                f"SELECT definition_json,definition_hash FROM {table} "
                "WHERE feature_version=? LIMIT 2",
                [FEATURE_VERSION],
            ).fetchall()
            if not definitions:
                target.execute(
                    f"INSERT INTO {table} VALUES (?,?,?,?,?)",
                    [FEATURE_VERSION, definition, definition_hash, job, datetime.now(UTC)],
                )
            elif definitions != [(definition, definition_hash)]:
                raise ValueError("RESEARCH_IV_DEFINITION_VERSION_CONTENT_MISMATCH")
            prior = next((row for row in rows if row[0] == key), None)
            inserted = prior is None
            if prior is not None:
                if prior[8:10] != (terms_json, result_json):
                    raise ValueError("RESEARCH_IV_EXACT_RETRY_CONTENT_MISMATCH")
            else:
                if len(rows) >= MAX_BUILDS:
                    raise ValueError("RESEARCH_IV_BUILD_HISTORY_LIMIT")
                target.execute(
                    f"INSERT INTO {_name(target, 'gold', 'research_iv_builds')} "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [
                        key,
                        group,
                        len(rows) + 1,
                        FEATURE_VERSION,
                        option_build_id,
                        spot_build_id,
                        terms_pin,
                        definition_hash,
                        terms_json,
                        result_json,
                        canonical([row[0] for row in rows]),
                        job,
                        datetime.now(UTC),
                        None,
                        None,
                    ],
                )
            attempts = _name(target, "gold", "research_iv_attempts")
            target.execute(f"INSERT INTO {attempts} VALUES (?,?,?)", [job, group, key])
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise
    return {
        "build_id": key,
        "input_id": group,
        "job_id": job,
        "inserted": inserted,
        "status": candidate.status,
        "publication_asserted": False,
        "decision_eligibility_asserted": False,
    }


def read_research_iv_archive(target: Any, *, build_id_pin: str) -> ResearchIvArchive:
    if not pin(build_id_pin):
        raise ValueError("EXACT_RESEARCH_IV_ARCHIVE_BUILD_PIN_REQUIRED")
    definition = _definition()
    definition_hash = sha(definition.encode())
    target.execute("BEGIN TRANSACTION")
    try:
        global_fingerprint = _global(target, definition)
        found = target.execute(
            f"SELECT input_id FROM {_name(target, 'gold', 'research_iv_builds')} "
            "WHERE build_id=? LIMIT 2",
            [build_id_pin],
        ).fetchall()
        if len(found) != 1:
            raise IvArchiveReviewRequired("RESEARCH_IV_EXACT_ARCHIVED_BUILD_NOT_FOUND")
        rows, scope_fingerprint = _scope(target, found[0][0], definition_hash)
        fingerprint = sha(canonical([VERSION, global_fingerprint, scope_fingerprint]).encode())
        selected = next(row for row in rows if row[0] == build_id_pin)
        head = rows[-1][0]
        target.execute("COMMIT")
    except BaseException:
        target.execute("ROLLBACK")
        raise
    is_head = head == build_id_pin
    return ResearchIvArchive(
        VERSION,
        build_id_pin,
        found[0][0],
        "verified_archived_head" if is_head else "review_required",
        ("EXACT_ARCHIVED_RECORDING_HEAD",) if is_head else ("ARCHIVED_IV_PIN_NOT_RETAINED_HEAD",),
        head,
        checked_json(selected[9])["status"],
        selected[9],
        selected[8],
        fingerprint,
        archived_pin_is_head=is_head,
    )
