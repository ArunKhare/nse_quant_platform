"""Bounded whole native capture-database evidence observation, not provenance authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

VERSION = "admission-capture-database-frontier@1"
MAX_TEXT_CELL = 131072
MAX_BLOB_CELL = 16777216
MAX_BLOB_TOTAL = 134217728
MAX_DOCUMENT_BYTES = 8388608
# Fixed native @1 column order. No silent schema repair or extension acceptance.
TABLES: dict[tuple[str, str], tuple[str, ...]] = {
    ("decision_inputs", "admission_schema_versions"): ("version",),
    ("decision_inputs", "admission_contracts"): (
        "contract_name",
        "contract_version",
        "fingerprint",
        "contract_json",
        "recorded_at",
        "first_job_id",
    ),
    ("decision_inputs", "admission_definitions"): (
        "policy_version",
        "definition_fingerprint",
        "definition_json",
        "recorded_at",
        "first_job_id",
    ),
    ("decision_inputs", "admission_receipts"): (
        "receipt_id",
        "request_revision_id",
        "store_version",
        "policy_version",
        "definition_fingerprint",
        "publication_id",
        "use_case",
        "request_knowledge_cutoff",
        "request_economic_at",
        "input_sha256",
        "source_evidence_fingerprint",
        "bundle_id",
        "status",
        "reason_codes_json",
        "research_analysis_permitted",
        "decision_eligibility_asserted",
        "receipt_byte_count",
        "receipt_bytes",
        "supersedes_json",
        "recorded_at",
        "first_job_id",
    ),
    ("decision_inputs", "admission_attempts"): (
        "job_id",
        "receipt_id",
        "input_sha256",
        "recorded_at",
    ),
    ("medallion_audit", "schema_versions"): ("version", "applied_at"),
    ("medallion_audit", "dataset_contracts"): (
        "dataset_name",
        "contract_version",
        "fingerprint",
        "contract_json",
        "registered_at",
    ),
    ("medallion_audit", "jobs"): (
        "job_id",
        "parent_job_id",
        "command_name",
        "actor_id",
        "scope_ref",
        "code_revision",
        "config_hash",
        "created_at",
    ),
    ("medallion_audit", "job_events"): (
        "job_id",
        "event_index",
        "state",
        "recorded_at",
        "reason_code",
    ),
}
LIMITS = {key: 2000 for key in TABLES}
LIMITS[("decision_inputs", "admission_receipts")] = 1001
LIMITS[("medallion_audit", "job_events")] = 6000


class FrontierReviewRequired(ValueError):
    """Coverage/shape failure; never a policy rejection or an all-clear."""


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _canonical(value: object) -> str:
    def clock(item: object) -> str:
        if not isinstance(item, datetime) or item.tzinfo is None or item.utcoffset() is None:
            raise FrontierReviewRequired("FRONTIER_UNSUPPORTED_OR_NAIVE_VALUE")
        return item.astimezone(UTC).isoformat()

    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=clock)


@dataclass(frozen=True)
class AdmissionFrontier:
    version: str
    fingerprint: str
    table_row_counts: tuple[tuple[str, int], ...]
    hashed_blob_bytes: int
    document_bytes: int
    coverage: str = "ENTIRE_DEDICATED_CAPTURE_DATABASE_NATIVE_TABLE_ROWS"
    provenance_verified: bool = False
    decision_eligibility_asserted: bool = False
    authenticity_asserted: bool = False


def observe_admission_frontier(captures: Any) -> AdmissionFrontier:
    """Owned file-backed read-only connection; no outer transaction.

    One transaction covers inventories, schema metadata and all rows in all nine
    native tables, including failed/unlinked jobs, other requests and registry
    origins. No outcome/success filter. SQL failures propagate. Payload BLOBs stay
    in DuckDB: hash exact bytes there. This scanner does not verify lifecycles,
    graph semantics, payload codec or source truth: native readers still must.
    """
    row = captures.execute("SELECT current_database()").fetchone()
    databases = captures.execute("PRAGMA database_list").fetchall()
    if row is None or not any(r[1] == row[0] and r[2] for r in databases):
        raise FrontierReviewRequired("FRONTIER_FILE_BACKED_DATABASE_REQUIRED")
    catalog = row[0]
    captures.execute("BEGIN TRANSACTION")
    try:
        inventory = captures.execute(
            "SELECT table_schema,table_name,table_type FROM information_schema.tables "
            "WHERE table_catalog=current_database() ORDER BY table_schema,table_name LIMIT 10"
        ).fetchall()
        if inventory != [(s, t, "BASE TABLE") for s, t in sorted(TABLES)]:
            raise FrontierReviewRequired("FRONTIER_UNSUPPORTED_OBJECT_INVENTORY")
        payload: list[object] = [VERSION]
        counts: list[tuple[str, int]] = []
        blob_total = text_total = document_size = 0
        for (schema, table), expected_columns in sorted(TABLES.items()):
            columns = captures.execute(
                "SELECT column_name,data_type,is_nullable FROM information_schema.columns "
                "WHERE table_catalog=current_database() AND table_schema=? AND table_name=? "
                "ORDER BY ordinal_position LIMIT 65",
                [schema, table],
            ).fetchall()
            if tuple(c[0] for c in columns) != expected_columns or any(
                c[1]
                not in {
                    "VARCHAR",
                    "BLOB",
                    "INTEGER",
                    "BIGINT",
                    "BOOLEAN",
                    "TIMESTAMP WITH TIME ZONE",
                }
                for c in columns
            ):
                raise FrontierReviewRequired("FRONTIER_UNSUPPORTED_COLUMN_SHAPE")
            qualified = ".".join(map(_quote, (catalog, schema, table)))
            limit = LIMITS[(schema, table)]
            count = captures.execute(f"SELECT count(*) FROM {qualified}").fetchone()[0]
            if count > limit:
                raise FrontierReviewRequired("FRONTIER_ROW_BOUND_REVIEW_REQUIRED")
            projection: list[str] = []
            for column, kind, _nullable in columns:
                name = _quote(column)
                if kind in {"VARCHAR", "BLOB"}:
                    length = (
                        f"octet_length(encode({name}))"
                        if kind == "VARCHAR"
                        else (f"octet_length({name})")
                    )
                    size = captures.execute(
                        f"SELECT coalesce(sum({length}),0),coalesce(max({length}),0) "
                        f"FROM {qualified}"
                    ).fetchone()
                    if kind == "VARCHAR":
                        text_total += size[0]
                        if size[1] > MAX_TEXT_CELL or text_total > MAX_DOCUMENT_BYTES:
                            raise FrontierReviewRequired("FRONTIER_TEXT_BOUND_REVIEW_REQUIRED")
                    else:
                        blob_total += size[0]
                        if size[1] > MAX_BLOB_CELL or blob_total > MAX_BLOB_TOTAL:
                            raise FrontierReviewRequired("FRONTIER_BLOB_BOUND_REVIEW_REQUIRED")
                if kind == "BLOB":
                    projection.extend((f"sha256({name})", f"octet_length({name})"))
                else:
                    projection.append(name)
            rows = captures.execute(
                f"SELECT {','.join(projection)} FROM {qualified} LIMIT ?",
                [limit + 1],
            ).fetchall()
            if len(rows) != count:
                raise FrontierReviewRequired("FRONTIER_INCOMPLETE_ROW_COVERAGE")
            # Sorting exact canonical rows avoids locale, insertion order and NULL sort choices.
            encoded_rows = sorted(_canonical(r) for r in rows)
            part = [schema, table, columns, encoded_rows]
            document_size += len(_canonical(part).encode())
            if document_size > MAX_DOCUMENT_BYTES:
                raise FrontierReviewRequired("FRONTIER_DOCUMENT_BOUND_REVIEW_REQUIRED")
            payload.append(part)
            counts.append((schema + "." + table, count))
        raw = _canonical(payload).encode()
        if len(raw) > MAX_DOCUMENT_BYTES:
            raise FrontierReviewRequired("FRONTIER_DOCUMENT_BOUND_REVIEW_REQUIRED")
        fingerprint = hashlib.sha256(raw).hexdigest()
        captures.execute("COMMIT")
    except BaseException:
        captures.execute("ROLLBACK")
        raise
    return AdmissionFrontier(VERSION, fingerprint, tuple(counts), blob_total, len(raw))
