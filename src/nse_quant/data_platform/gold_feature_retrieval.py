"""Availability-aware, versioned Gold feature retrieval with exact replay.

Retrieves only Gold feature revisions whose Silver revision and Bronze capture
were available at the requested decision time. Produces an immutable decision
bundle and supports exact replay. No decision eligibility, publication, live
acquisition, or trading authority is asserted.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

import duckdb

FEATURE_SET = "option_chain_features@1"
REQUIRED_CONTEXT_KEYS = {
    "version",
    "silver_revision_id",
    "silver_context_sha256",
    "bronze_pins",
    "feature",
}
REQUIRED_BRONZE_PINS = {
    "snapshot_id",
    "capture_event_id",
    "envelope_hash",
    "recording_fingerprint",
    "source_label",
}


class Rejected(ValueError):
    """Explicit retrieval rejection; callers must not treat this as authorization."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _pin(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _catalog(conn: duckdb.DuckDBPyConnection) -> str:
    row = conn.execute("SELECT current_catalog()").fetchone()
    if row is None:
        raise Rejected("CURRENT_CATALOG_UNAVAILABLE")
    return str(row[0])


def _qualify(conn: duckdb.DuckDBPyConnection, schema: str, table: str) -> str:
    return f'"{_catalog(conn)}"."{schema}"."{table}"'


def _readonly(conn: duckdb.DuckDBPyConnection) -> None:
    paths = conn.execute("SELECT path FROM duckdb_databases() WHERE database_name=current_database()").fetchall()
    if len(paths) != 1 or not paths[0][0]:
        raise Rejected("FILE_BACKED_GOLD_REQUIRED")


def _validate_context(document: object, expected_feature_revision_id: Any) -> dict[str, Any]:
    if not isinstance(document, dict) or set(document) != REQUIRED_CONTEXT_KEYS:
        raise Rejected("GOLD_CONTEXT_SCHEMA_MISMATCH")
    if document["version"] != FEATURE_SET:
        raise Rejected("GOLD_FEATURE_SET_MISMATCH")
    if not _pin(document["silver_revision_id"]):
        raise Rejected("SILVER_REVISION_PIN_INVALID")
    if not _pin(document["silver_context_sha256"]):
        raise Rejected("SILVER_CONTEXT_PIN_INVALID")
    bronze = document["bronze_pins"]
    feature = document["feature"]
    if not isinstance(bronze, dict) or not REQUIRED_BRONZE_PINS.issubset(bronze):
        raise Rejected("BRONZE_LINEAGE_INCOMPLETE")
    if not all(
        _pin(bronze[key]) for key in ("snapshot_id", "capture_event_id", "envelope_hash", "recording_fingerprint")
    ):
        raise Rejected("BRONZE_PIN_INVALID")
    if not isinstance(feature, dict) or feature.get("version") != FEATURE_SET:
        raise Rejected("GOLD_FEATURE_RECORD_MISMATCH")
    if feature.get("decision_eligibility_asserted") is not False:
        raise Rejected("DECISION_ELIGIBILITY_ASSERTED")
    derived_revision = _sha(
        _canonical(
            [
                FEATURE_SET,
                document["silver_revision_id"],
                document["silver_context_sha256"],
                bronze["recording_fingerprint"],
            ]
        )
    )
    if derived_revision != expected_feature_revision_id:
        raise Rejected("GOLD_REVISION_DERIVATION_MISMATCH")
    return document


def retrieve_gold_feature(
    gold: duckdb.DuckDBPyConnection,
    *,
    underlying: str,
    as_of: datetime,
    feature_set: str = FEATURE_SET,
) -> dict[str, Any]:
    """Retrieve the latest available Gold feature revision at an exact decision time."""
    if feature_set != FEATURE_SET:
        raise Rejected("UNSUPPORTED_FEATURE_SET")
    if not underlying or not underlying.strip():
        raise Rejected("UNDERLYING_REQUIRED")
    if as_of.tzinfo is None:
        raise Rejected("AWARE_DECISION_TIME_REQUIRED")
    _readonly(gold)
    sets = _qualify(gold, "gold", "option_chain_feature_sets")
    observations = _qualify(gold, "gold", "option_chain_feature_observations")
    rows = gold.execute(
        f"""
        SELECT s.feature_revision_id, s.feature_context, s.feature_context_sha256,
               s.recorded_at, o.feature_record
        FROM {sets} s
        JOIN {observations} o
          ON o.feature_revision_id = s.feature_revision_id
        WHERE s.recorded_at <= ?
        ORDER BY s.recorded_at DESC, s.feature_revision_id DESC
        LIMIT 100
        """,
        [as_of],
    ).fetchall()
    row = None
    for candidate in rows:
        try:
            candidate_document = json.loads(bytes(candidate[1]))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        candidate_feature = candidate_document.get("feature")
        if (
            isinstance(candidate_feature, dict)
            and candidate_feature.get("underlying") == underlying
            and candidate_document.get("version") == FEATURE_SET
        ):
            row = candidate
            break
    if row is None:
        return {
            "status": "FEATURE_NOT_AVAILABLE",
            "underlying": underlying,
            "as_of": as_of.isoformat(),
            "feature_set": feature_set,
            "decision_eligibility_asserted": False,
        }
    feature_revision_id, context_bytes, stored_hash, recorded_at, record_bytes = row
    context = bytes(context_bytes)
    if _sha(context) != stored_hash:
        raise Rejected("GOLD_CONTEXT_HASH_MISMATCH")
    try:
        document = json.loads(context)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Rejected("GOLD_CONTEXT_MALFORMED") from exc

    if not _pin(feature_revision_id):
        raise Rejected("GOLD_REVISION_PIN_REQUIRED")

    document = _validate_context(document, feature_revision_id)
    feature = document["feature"]
    if feature.get("underlying") != underlying:
        raise Rejected("UNDERLYING_MISMATCH")
    if bytes(record_bytes) != context:
        raise Rejected("GOLD_OBSERVATION_CONTEXT_MISMATCH")
    bundle = {
        "version": "gold_decision_bundle@1",
        "feature_set": FEATURE_SET,
        "underlying": underlying,
        "as_of": as_of.isoformat(),
        "available_at": recorded_at.isoformat(),
        "feature_revision_id": feature_revision_id,
        "feature_context_sha256": stored_hash,
        "silver_revision_id": document["silver_revision_id"],
        "silver_context_sha256": document["silver_context_sha256"],
        "bronze_pins": document["bronze_pins"],
        "feature": feature,
        "decision_eligibility_asserted": False,
    }
    return {
        "status": "FEATURE_AVAILABLE",
        "bundle": bundle,
        "bundle_sha256": _sha(_canonical(bundle)),
        "decision_eligibility_asserted": False,
    }


def replay_gold_feature(
    gold: duckdb.DuckDBPyConnection,
    *,
    bundle: dict[str, Any],
    expected_bundle_sha256: str,
) -> dict[str, Any]:
    """Exactly replay a previously retrieved Gold decision bundle."""
    if not _pin(expected_bundle_sha256):
        raise Rejected("EXACT_BUNDLE_PIN_REQUIRED")
    if _sha(_canonical(bundle)) != expected_bundle_sha256:
        raise Rejected("BUNDLE_CONTENT_CHANGED")
    if bundle.get("version") != "gold_decision_bundle@1":
        raise Rejected("UNSUPPORTED_BUNDLE_VERSION")
    if bundle.get("feature_set") != FEATURE_SET:
        raise Rejected("UNSUPPORTED_FEATURE_SET")

    feature_revision_id = bundle.get("feature_revision_id")
    if not _pin(feature_revision_id):
        raise Rejected("GOLD_REVISION_PIN_REQUIRED")
    _readonly(gold)
    sets = _qualify(gold, "gold", "option_chain_feature_sets")
    observations = _qualify(gold, "gold", "option_chain_feature_observations")
    row = gold.execute(
        f"""
        SELECT s.feature_context, s.feature_context_sha256, o.feature_record
        FROM {sets} s
        JOIN {observations} o
          ON o.feature_revision_id = s.feature_revision_id
        WHERE s.feature_revision_id = ?
        LIMIT 2
        """,
        [feature_revision_id],
    ).fetchall()
    if len(row) != 1:
        raise Rejected("EXACT_GOLD_REVISION_REQUIRED")
    context = bytes(row[0][0])
    stored_hash = row[0][1]
    record = bytes(row[0][2])
    if _sha(context) != stored_hash or context != record:
        raise Rejected("GOLD_CONTEXT_REPLAY_MISMATCH")
    try:
        document = json.loads(context)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Rejected("GOLD_CONTEXT_MALFORMED") from exc

    feature_revision_id = bundle.get("feature_revision_id")

    if not _pin(feature_revision_id):
        raise Rejected("GOLD_REVISION_PIN_REQUIRED")
    document = _validate_context(document, feature_revision_id)
    if document["feature"] != bundle.get("feature"):
        raise Rejected("GOLD_FEATURE_REPLAY_MISMATCH")
    if document["silver_revision_id"] != bundle.get("silver_revision_id"):
        raise Rejected("SILVER_LINEAGE_REPLAY_MISMATCH")
    if document["bronze_pins"] != bundle.get("bronze_pins"):
        raise Rejected("BRONZE_LINEAGE_REPLAY_MISMATCH")
    return {
        "status": "REPLAYED",
        "feature_revision_id": feature_revision_id,
        "feature_context_sha256": stored_hash,
        "bundle_sha256": expected_bundle_sha256,
        "feature": document["feature"],
        "decision_eligibility_asserted": False,
    }
