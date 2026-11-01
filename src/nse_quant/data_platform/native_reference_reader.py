"""Read-only pinned row evidence, not publication, historical validity or contract identity."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from nse_quant.data_platform.reference_supersession import (
    MAX_ASSESSMENTS,
    RESOLVER_VERSION,
    AssessmentNode,
    resolve_supersession,
    valid_hash,
)

MAX_RESULT_BYTES = 134_217_728
MAX_TOKEN_CANDIDATES = 1000


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _name(conn: Any, schema: str, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise RuntimeError("CATALOG_UNAVAILABLE")
    return ".".join('"' + str(p).replace('"', '""') + '"' for p in (row[0], schema, table))


def _json(text: str) -> Any:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    def invalid(_value: str) -> Any:
        raise ValueError("NONFINITE_JSON")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


@dataclass(frozen=True)
class NativeReferenceRowPin:
    assessment_revision_id: str
    row_ordinal: int
    source_fields_hash: str


@dataclass(frozen=True)
class NativeReferenceLookup:
    resolver_version: str
    assessment_revision_id: str
    instrument_token: int
    status: str
    reason_code: str
    active_revision_ids: tuple[str, ...] = ()
    candidates: tuple[NativeReferenceRowPin, ...] = ()
    evidence_mode: str = "PINNED_CURRENT_EVIDENCE_ONLY"
    canonical_contract_id: None = None
    historical_validity_asserted: bool = False
    publication_asserted: bool = False


def _verify_source(
    bronze: Any,
    row: dict[str, Any],
) -> tuple[str, str, str, str, str | None, str | None]:
    """Recompute with the EXACT currently supported versions, never silently upgrade."""
    from dataclasses import asdict

    from nse_quant.data_platform.native_reference_decode import (
        CSV_VERSION,
        DECODER_VERSION,
        canonical,
        normalize_native_content,
    )
    from nse_quant.data_platform.native_reference_evidence import (
        ReferencePins,
        inspect_reference_pair,
    )
    from nse_quant.data_platform.native_reference_silver import NORMALIZER_VERSION

    if row["versions"] != [NORMALIZER_VERSION, DECODER_VERSION, CSV_VERSION]:
        return "UNSUPPORTED_NORMALIZATION_VERSION", "", "", "", None, None
    pins = ReferencePins(*row["pins"])
    evidence = inspect_reference_pair(bronze, pins)
    if evidence.gate_code != "VERIFIED":
        return "SOURCE_" + evidence.gate_code, "", "", "", None, None
    result = normalize_native_content(evidence.raw_body, evidence.headers)
    return (
        "VERIFIED",
        evidence.evidence_json,
        evidence.source_times_json,
        canonical(asdict(result)),
        evidence.body_payload_hash,
        evidence.metadata_payload_hash,
    )


def lookup_native_reference(
    bronze: Any,
    silver: Any,
    *,
    assessment_revision_id: str,
    instrument_token: int,
) -> NativeReferenceLookup:
    """Both connections must be read-only, owned by this sequential caller.

    Silver history is captured in one transaction. Bronze verification is a separate
    read snapshot, NOT an atomic cross-database lock or a decision publication barrier.
    """
    if not valid_hash(assessment_revision_id):
        raise ValueError("EXACT_ASSESSMENT_REVISION_REQUIRED")
    if type(instrument_token) is not int or not 0 < instrument_token < 2**32:
        raise ValueError("INVALID_PROVIDER_TOKEN")

    def outcome(
        reason: str,
        active: tuple[str, ...] = (),
        candidates: tuple[NativeReferenceRowPin, ...] = (),
        status: str = "blocked",
    ) -> NativeReferenceLookup:
        return NativeReferenceLookup(
            RESOLVER_VERSION,
            assessment_revision_id,
            instrument_token,
            status,
            reason,
            active,
            candidates,
        )

    target = _name(silver, "silver", "kite_http_reference_results")
    silver.execute("BEGIN TRANSACTION")
    try:
        pin = silver.execute(
            f"SELECT input_revision_id FROM {target} WHERE revision_id=?", [assessment_revision_id]
        ).fetchone()
        if pin is None:
            silver.execute("COMMIT")
            return outcome("ASSESSMENT_NOT_FOUND")
        history = silver.execute(
            f"SELECT revision_id,input_revision_id,"
            f"CASE WHEN length(supersedes_json)<=100000 THEN supersedes_json ELSE NULL END "
            f"FROM {target} WHERE input_revision_id=? ORDER BY revision_id LIMIT ?",
            [pin[0], MAX_ASSESSMENTS + 1],
        ).fetchall()
        if len(history) > MAX_ASSESSMENTS:
            silver.execute("COMMIT")
            return outcome("ASSESSMENT_HISTORY_LIMIT")
        try:
            nodes: list[AssessmentNode] = []
            for revision, group, links_json in history:
                if links_json is None:
                    raise ValueError("OVERSIZED_LINKS")
                links = _json(links_json)
                if not isinstance(links, list):
                    raise ValueError("INVALID_LINKS")
                nodes.append(AssessmentNode(revision, group, tuple(links)))
        except (ValueError, TypeError, RecursionError):
            silver.execute("COMMIT")
            return outcome("INVALID_SUPERSESSION_EVIDENCE")
        graph = resolve_supersession(tuple(nodes), assessment_revision_id)
        if graph.reason_code != "ACTIVE_PINNED_ASSESSMENT":
            silver.execute("COMMIT")
            return outcome(graph.reason_code, graph.active_revision_ids)
        # Deliberately AFTER graph resolution: no classification/job-state WHERE clause above.
        record = silver.execute(
            f"SELECT schema_version,source_observation_id,body_envelope_hash,body_payload_hash,"
            f"metadata_capture_event_id,metadata_envelope_hash,metadata_payload_hash,"
            f"normalizer_version,content_decoder_version,csv_version,gate_fingerprint,"
            f"CASE WHEN length(gate_evidence_json)<=131072 THEN gate_evidence_json ELSE NULL END,"
            f"CASE WHEN length(source_times_json)<=32768 THEN source_times_json ELSE NULL END,"
            f"classification,reason_code,record_count,"
            f"CASE WHEN octet_length(encode(result_json))<=? THEN result_json ELSE NULL END,"
            f"first_job_id FROM {target} WHERE revision_id=?",
            [MAX_RESULT_BYTES, assessment_revision_id],
        ).fetchone()
        if record is None:
            raise RuntimeError("PINNED_ROW_DISAPPEARED")
        jobs = _name(silver, "medallion_audit", "jobs")
        events = _name(silver, "medallion_audit", "job_events")
        job = silver.execute(
            f"SELECT command_name,scope_ref,config_hash FROM {jobs} WHERE job_id=?", [record[17]]
        ).fetchone()
        state = silver.execute(
            f"SELECT state FROM {events} WHERE job_id=? ORDER BY event_index DESC LIMIT 1",
            [record[17]],
        ).fetchone()
        silver.execute("COMMIT")
    except BaseException:
        silver.execute("ROLLBACK")
        raise
    active = graph.active_revision_ids
    if record[0] != 1:
        return outcome("UNSUPPORTED_ASSESSMENT_SCHEMA", active)
    versions = list(record[7:10])
    pins = [record[1], record[2], record[4], record[5]]
    if any(not valid_hash(p) for p in pins):
        return outcome("INVALID_SOURCE_PINS", active)
    pin_dict = dict(
        zip(
            (
                "body_capture_event_id",
                "body_envelope_hash",
                "metadata_capture_event_id",
                "metadata_envelope_hash",
            ),
            pins,
            strict=True,
        )
    )
    input_id = _hash([pin_dict, versions])
    if input_id != pin[0] or _hash([input_id, record[10]]) != assessment_revision_id:
        return outcome("ASSESSMENT_IDENTITY_MISMATCH", active)
    if job != (
        "normalize.kite_native_reference@1",
        "sha256:" + input_id,
        _hash(versions),
    ) or state != ("SUCCEEDED",):
        return outcome("NORMALIZATION_AUDIT_NOT_VERIFIED", active)
    if record[11] is None or record[12] is None or record[16] is None:
        return outcome("ASSESSMENT_RESOURCE_LIMIT", active)
    if hashlib.sha256(record[11].encode()).hexdigest() != record[10]:
        return outcome("GATE_FINGERPRINT_MISMATCH", active)
    if record[13] != "normalized":
        return outcome("ASSESSMENT_NOT_NORMALIZED", active)
    row = {"versions": versions, "pins": pins}
    verified = _verify_source(bronze, row)
    if verified[0] != "VERIFIED":
        return outcome(verified[0], active)
    if verified[1:] != (record[11], record[12], record[16], record[3], record[6]):
        return outcome("SOURCE_ASSESSMENT_CONTENT_MISMATCH", active)
    try:
        parsed = _json(record[16])
        rows = parsed["rows"]
        if (
            parsed["classification"] != "normalized"
            or parsed["reason_code"] != record[14]
            or not isinstance(rows, list)
            or len(rows) != record[15]
            or len(rows) > 200000
        ):
            return outcome("RESULT_CONTRACT_MISMATCH", active)
        selected: list[NativeReferenceRowPin] = []
        for ordinal, source_row in enumerate(rows):
            if (
                type(source_row["row_ordinal"]) is not int
                or source_row["row_ordinal"] != ordinal
                or type(source_row["instrument_token"]) is not int
                or not 0 < source_row["instrument_token"] < 2**32
                or not valid_hash(source_row["source_fields_hash"])
            ):
                return outcome("ROW_REFERENCE_CONTRACT_MISMATCH", active)
            if source_row["instrument_token"] == instrument_token:
                if len(selected) >= MAX_TOKEN_CANDIDATES:
                    return outcome("TOKEN_CANDIDATE_LIMIT", active)
                selected.append(
                    NativeReferenceRowPin(
                        assessment_revision_id, ordinal, source_row["source_fields_hash"]
                    )
                )
        candidates = tuple(selected)
    except (ValueError, TypeError, KeyError, RecursionError):
        return outcome("MALFORMED_NORMALIZATION_RESULT", active)
    if not candidates:
        return outcome("TOKEN_NOT_IN_PINNED_ASSESSMENT", active, status="unresolved")
    if len(candidates) > 1:
        return outcome("MULTIPLE_TOKEN_ROWS", active, candidates, "ambiguous")
    return outcome("UNIQUE_TOKEN_ROW", active, candidates, "matched")
