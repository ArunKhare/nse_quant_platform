"""Invalidation-first, source-recomputed native Gold evidence; never publication."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform.gold_quote_features import (
    DEFINITION,
    DEFINITION_FINGERPRINT,
    FEATURE_VERSION,
    GoldQuoteCandidate,
    build_quote_price_candidate,
)
from nse_quant.data_platform.gold_quote_store import COMMAND, STORE_VERSION
from nse_quant.data_platform.reference_supersession import (
    MAX_ASSESSMENTS,
    AssessmentNode,
    resolve_supersession,
    valid_hash,
)

READER_VERSION = "gold-provider-price-consumer@1"
MAX_RESULT_BYTES = 1_048_576
MAX_ATTEMPTS = 1000


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _json(raw: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    def invalid(_value: str) -> Any:
        raise ValueError("NONFINITE_JSON")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def _name(conn: Any, schema: str, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise RuntimeError("CATALOG_UNAVAILABLE")
    return ".".join('"' + str(p).replace('"', '""') + '"' for p in (row[0], schema, table))


def _instant(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("AWARE_TIME_REQUIRED")
    return value.astimezone(UTC).isoformat()


@dataclass(frozen=True)
class GoldQuoteEvidence:
    reader_version: str
    build_id: str
    status: str
    reason_code: str
    active_build_ids: tuple[str, ...] = ()
    successful_attempt_job_ids: tuple[str, ...] = ()
    candidate: GoldQuoteCandidate | None = None
    evidence_fingerprint: str | None = None
    publication_asserted: bool = False
    historical_validity_asserted: bool = False
    decision_eligibility_asserted: bool = False


def read_quote_price_build(
    bronze: Any,
    frame_silver: Any,
    reference_silver: Any,
    assessments: Any,
    gold: Any,
    *,
    build_id: str,
) -> GoldQuoteEvidence:
    """Owned read-only connections, no enclosing transactions; Gold separate.

    Gold metadata is one read snapshot; source revalidation follows separately,
    NOT an atomic cross-database barrier or an as-recorded historical replay.
    All linked active-build attempts must be terminal, with at least one success.
    Definition origin needs its own successful linked job, even for another input.
    """
    if not valid_hash(build_id):
        raise ValueError("EXACT_GOLD_BUILD_PIN_REQUIRED")
    gp = {r[2] for r in gold.execute("PRAGMA database_list").fetchall() if r[2]}
    for source in (bronze, frame_silver, reference_silver, assessments):
        sp = {r[2] for r in source.execute("PRAGMA database_list").fetchall() if r[2]}
        if source is gold or gp & sp:
            raise ValueError("SEPARATE_GOLD_DATABASE_REQUIRED")

    def blocked(reason: str, active: tuple[str, ...] = ()) -> GoldQuoteEvidence:
        return GoldQuoteEvidence(READER_VERSION, build_id, "blocked", reason, active)

    builds = _name(gold, "gold", "quote_price_builds")
    definitions = _name(gold, "gold", "quote_price_definitions")
    attempts = _name(gold, "gold", "quote_price_build_attempts")
    schema = _name(gold, "gold", "quote_price_schema_versions")
    audit_schema = _name(gold, "medallion_audit", "schema_versions")
    jobs = _name(gold, "medallion_audit", "jobs")
    events = _name(gold, "medallion_audit", "job_events")
    contracts = _name(gold, "medallion_audit", "dataset_contracts")
    gold.execute("BEGIN TRANSACTION")
    try:
        schema_rows = gold.execute(f"SELECT version FROM {schema} LIMIT 2").fetchall()
        audit_rows = gold.execute(f"SELECT version FROM {audit_schema} LIMIT 2").fetchall()
        if schema_rows != [(1,)] or audit_rows != [(1,)]:
            gold.execute("COMMIT")
            return blocked("UNSUPPORTED_GOLD_SCHEMA")
        pin = gold.execute(
            f"SELECT input_revision_id FROM {builds} WHERE build_id=?",
            [build_id],
        ).fetchone()
        if pin is None:
            gold.execute("COMMIT")
            return blocked("GOLD_BUILD_NOT_FOUND")
        history = gold.execute(
            f"SELECT build_id,input_revision_id,CASE WHEN "
            f"octet_length(encode(supersedes_json))<=100000 THEN supersedes_json ELSE NULL END "
            f"FROM {builds} WHERE input_revision_id=? ORDER BY build_id LIMIT ?",
            [pin[0], MAX_ASSESSMENTS + 1],
        ).fetchall()
        if len(history) > MAX_ASSESSMENTS:
            gold.execute("COMMIT")
            return blocked("GOLD_HISTORY_LIMIT")
        try:
            nodes: list[AssessmentNode] = []
            for revision, group, links_json in history:
                links = _json(links_json)
                if not isinstance(links, list):
                    raise ValueError("INVALID_LINKS")
                nodes.append(AssessmentNode(revision, group, tuple(links)))
        except (ValueError, TypeError, RecursionError):
            gold.execute("COMMIT")
            return blocked("INVALID_GOLD_HISTORY")
        graph = resolve_supersession(tuple(nodes), build_id)
        if graph.reason_code != "ACTIVE_PINNED_ASSESSMENT":
            gold.execute("COMMIT")
            return blocked("GOLD_" + graph.reason_code, graph.active_revision_ids)
        record = gold.execute(
            f"SELECT input_revision_id,source_assessment_revision_id,store_version,"
            f"feature_version,definition_fingerprint,status,reason_code,"
            f"source_evidence_fingerprint,CASE WHEN octet_length(encode(result_json))<=? "
            f"THEN result_json ELSE NULL END,event_ts,last_trade_time,published_at,"
            f"effective_from,effective_to,first_job_id FROM {builds} WHERE build_id=?",
            [MAX_RESULT_BYTES, build_id],
        ).fetchone()
        contract = gold.execute(
            f"SELECT fingerprint,contract_json FROM {contracts} "
            "WHERE dataset_name='gold.quote_price_builds' AND contract_version='1'"
        ).fetchone()
        definition = gold.execute(
            f"SELECT definition_fingerprint,CASE WHEN octet_length(encode(definition_json))"
            f"<=32768 THEN definition_json ELSE NULL END,first_job_id "
            f"FROM {definitions} WHERE feature_version=?",
            [FEATURE_VERSION],
        ).fetchone()
        linked = gold.execute(
            f"SELECT a.job_id,j.command_name,j.scope_ref,j.config_hash,"
            f"(SELECT e.state FROM {events} e WHERE e.job_id=a.job_id "
            f"ORDER BY e.event_index DESC LIMIT 1) FROM {attempts} a "
            f"LEFT JOIN {jobs} j ON j.job_id=a.job_id "
            "WHERE a.build_id=? ORDER BY a.job_id LIMIT ?",
            [build_id, MAX_ATTEMPTS + 1],
        ).fetchall()
        origin: list[tuple[Any, ...]] = []
        if definition is not None:
            origin = gold.execute(
                f"SELECT b.build_id,b.input_revision_id,b.source_assessment_revision_id,"
                f"b.store_version,b.feature_version,b.definition_fingerprint,"
                f"j.command_name,j.scope_ref,j.config_hash,"
                f"(SELECT e.state FROM {events} e WHERE e.job_id=a.job_id "
                f"ORDER BY e.event_index DESC LIMIT 1) FROM {attempts} a "
                f"LEFT JOIN {builds} b ON b.build_id=a.build_id "
                f"LEFT JOIN {jobs} j ON j.job_id=a.job_id WHERE a.job_id=? LIMIT 2",
                [definition[2]],
            ).fetchall()
        gold.execute("COMMIT")
    except BaseException:
        gold.execute("ROLLBACK")
        raise
    active = graph.active_revision_ids
    if record is None:
        return blocked("PINNED_GOLD_BUILD_DISAPPEARED", active)
    expected_contract = {
        "name": "gold.quote_price_builds",
        "version": "1",
        "layer": "gold",
        "write_policy": "versioned_builds",
        "entity_keys": ["build_id"],
        "required_columns": ["build_id", "event_ts", "published_at", "feature_version"],
        "owner": "native_gold_quote_features",
    }
    if contract != (_hash(expected_contract), _canonical(expected_contract)):
        return blocked("GOLD_CONTRACT_NOT_VERIFIED", active)
    if (
        STORE_VERSION != "gold-provider-price-builds@1"
        or COMMAND != "build.provider_quote_prices@1"
        or FEATURE_VERSION != "provider-packet-price-fields@1"
        or record[2:5] != (STORE_VERSION, FEATURE_VERSION, DEFINITION_FINGERPRINT)
        or _hash(DEFINITION) != DEFINITION_FINGERPRINT
    ):
        return blocked("UNSUPPORTED_GOLD_BUILD_VERSION", active)
    versions = [STORE_VERSION, FEATURE_VERSION, DEFINITION_FINGERPRINT]
    if not valid_hash(record[1]) or _hash([record[1], versions]) != record[0]:
        return blocked("GOLD_INPUT_IDENTITY_MISMATCH", active)
    if definition is None or definition[:2] != (DEFINITION_FINGERPRINT, _canonical(DEFINITION)):
        return blocked("GOLD_DEFINITION_NOT_VERIFIED", active)
    if len(origin) != 1:
        return blocked("GOLD_DEFINITION_ORIGIN_MISSING", active)
    definition_origin = origin[0]
    if (
        not valid_hash(definition_origin[0])
        or not valid_hash(definition_origin[2])
        or definition_origin[1] != _hash([definition_origin[2], versions])
        or definition_origin[3:6] != (STORE_VERSION, FEATURE_VERSION, DEFINITION_FINGERPRINT)
        or definition_origin[6:10]
        != (
            COMMAND,
            "sha256:" + definition_origin[1],
            _hash(versions),
            "SUCCEEDED",
        )
    ):
        return blocked("GOLD_DEFINITION_AUDIT_NOT_VERIFIED", active)
    if any(value is not None for value in record[11:14]):
        return blocked("UNSUPPORTED_GOLD_TEMPORAL_CLAIMS", active)
    if len(linked) > MAX_ATTEMPTS:
        return blocked("GOLD_ATTEMPT_LIMIT", active)
    if not linked or record[14] not in {attempt[0] for attempt in linked}:
        return blocked("GOLD_ATTEMPT_LINEAGE_MISSING", active)
    succeeded: list[str] = []
    for job_id, command, scope, config, state in linked:
        if (command, scope, config) != (COMMAND, "sha256:" + record[0], _hash(versions)):
            return blocked("GOLD_ATTEMPT_AUDIT_MISMATCH", active)
        if state not in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return blocked("GOLD_ATTEMPT_NOT_TERMINAL", active)
        if state == "SUCCEEDED":
            succeeded.append(job_id)
    if not succeeded:
        return blocked("GOLD_NO_SUCCESSFUL_ATTEMPT", active)
    if record[8] is None:
        return blocked("GOLD_RESULT_LIMIT", active)
    try:
        value = _json(record[8])
        if not isinstance(value, dict) or _canonical(value) != record[8]:
            return blocked("INVALID_GOLD_RESULT", active)
        if (
            value["build_id"] != build_id
            or _hash(dict(value, build_id="")) != build_id
            or [
                value[key]
                for key in (
                    "source_assessment_revision_id",
                    "feature_version",
                    "definition_fingerprint",
                    "status",
                    "reason_code",
                    "source_evidence_fingerprint",
                )
            ]
            != [record[1], record[3], record[4], record[5], record[6], record[7]]
            or value["status"] not in {"candidate", "blocked"}
            or value["canonical_contract_id"] is not None
            or any(
                value[key] is not None
                for key in (
                    "published_at",
                    "effective_from",
                    "effective_to",
                )
            )
            or value["decision_eligibility_asserted"] is not False
        ):
            return blocked("GOLD_RESULT_IDENTITY_MISMATCH", active)
        if value["event_ts"] != _instant(record[9]) or value["last_trade_time"] != (
            _instant(record[10])
        ):
            return blocked("GOLD_EVENT_TIME_MISMATCH", active)
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        return blocked("MALFORMED_GOLD_RESULT", active)
    current = build_quote_price_candidate(
        bronze,
        frame_silver,
        reference_silver,
        assessments,
        assessment_revision_id=record[1],
    )
    current_json = _canonical(asdict(current))
    if current_json != record[8]:
        return blocked("CURRENT_GOLD_SOURCE_EVIDENCE_CHANGED", active)
    evidence_hash = _hash(
        [
            READER_VERSION,
            build_id,
            active,
            definition,
            origin,
            linked,
            current_json,
        ]
    )
    return GoldQuoteEvidence(
        READER_VERSION,
        build_id,
        "verified_current",
        "SOURCE_RECOMPUTED",
        active,
        tuple(succeeded),
        current,
        evidence_hash,
    )
