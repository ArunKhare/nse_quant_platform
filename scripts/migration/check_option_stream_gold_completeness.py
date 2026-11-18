"""Read-only completeness check for option-chain Gold feature set v1.

Validates:
- Gold feature-set, observation, attempt, and audit-job reconciliation.
- Registered Gold dataset contract.
- Complete audited job lifecycle.
- Feature context hash and canonical JSON integrity.
- Bronze and Silver lineage pins.
- Duplicate Silver revisions.
- Decision-eligibility and publication assertions.

Safety:
- Opens Gold read-only.
- No writes, no rebuild, no publication, no live acquisition, no trading.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import duckdb

EXPECTED_FEATURE_SET = "option_chain_features@1"
EXPECTED_CONTRACT = "gold.option_chain_features"
EXPECTED_CONTRACT_VERSION = "1"


def count(conn: duckdb.DuckDBPyConnection, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    if row is None:
        raise ValueError("EXPECTED_SCALAR_ROW")
    return int(row[0])


def _catalog(conn: duckdb.DuckDBPyConnection) -> str:
    row = conn.execute("SELECT current_catalog()").fetchone()
    if row is None:
        raise ValueError("CURRENT_CATALOG_UNAVAILABLE")
    return str(row[0])


def _qualify(conn: duckdb.DuckDBPyConnection, schema: str, table: str) -> str:
    return f'"{_catalog(conn)}"."{schema}"."{table}"'


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False).encode("utf-8")


def check_gold(conn: duckdb.DuckDBPyConnection) -> int:
    catalog = _catalog(conn)
    sets = _qualify(conn, "gold", "option_chain_feature_sets")
    observations = _qualify(conn, "gold", "option_chain_feature_observations")
    attempts = _qualify(conn, "gold", "option_chain_feature_attempts")
    jobs = _qualify(conn, "medallion_audit", "jobs")
    events = _qualify(conn, "medallion_audit", "job_events")
    contracts = _qualify(conn, "medallion_audit", "dataset_contracts")

    feature_sets = count(conn, f"SELECT COUNT(*) FROM {sets}")
    feature_observations = count(conn, f"SELECT COUNT(*) FROM {observations}")
    feature_attempts = count(conn, f"SELECT COUNT(*) FROM {attempts}")
    audit_jobs = count(conn, f"SELECT COUNT(*) FROM {jobs}")
    job_events = count(conn, f"SELECT COUNT(*) FROM {events}")

    contracts = count(
        conn,
        f"""
        SELECT COUNT(*) FROM {contracts}
        WHERE dataset_name = '{EXPECTED_CONTRACT}'
          AND contract_version = '{EXPECTED_CONTRACT_VERSION}'
        """,
    )

    completed_jobs = count(
        conn,
        f"""
        SELECT COUNT(*) FROM {jobs} j
        WHERE (
          SELECT count(*) FROM {events} e WHERE e.job_id = j.job_id
        ) = 3
          AND EXISTS (
            SELECT 1 FROM {events} e
            WHERE e.job_id = j.job_id AND e.state = 'PLANNED'
          )
          AND EXISTS (
            SELECT 1 FROM {events} e
            WHERE e.job_id = j.job_id AND e.state = 'RUNNING'
          )
          AND EXISTS (
            SELECT 1 FROM {events} e
            WHERE e.job_id = j.job_id AND e.state = 'SUCCEEDED'
          )
        """,
    )

    missing_observations = count(
        conn,
        f"""
        SELECT COUNT(*) FROM {sets} s
        WHERE NOT EXISTS (
          SELECT 1 FROM {observations} o
          WHERE o.feature_revision_id = s.feature_revision_id
        )
        """,
    )
    missing_attempts = count(
        conn,
        f"""
        SELECT COUNT(*) FROM {sets} s
        WHERE NOT EXISTS (
          SELECT 1 FROM {attempts} a
          WHERE a.feature_revision_id = s.feature_revision_id
        )
        """,
    )
    duplicate_silver_revisions = count(
        conn,
        f"""
        SELECT COUNT(*) FROM (
          SELECT silver_revision_id FROM {sets}
          GROUP BY silver_revision_id HAVING COUNT(*) > 1
        )
        """,
    )
    invalid_context_hash = count(
        conn,
        f"""
        SELECT COUNT(*) FROM {sets}
        WHERE feature_context_sha256 IS NULL
           OR length(feature_context_sha256) <> 64
        """,
    )

    context_mismatches = 0
    lineage_mismatches = 0
    eligibility_mismatches = 0
    rows = conn.execute(
        f"""
        SELECT feature_revision_id, feature_context, feature_context_sha256
        FROM {sets}
        ORDER BY feature_revision_id
        """
    ).fetchall()
    for _feature_revision_id, context_bytes, stored_hash in rows:
        context = bytes(context_bytes)
        actual_hash = hashlib.sha256(context).hexdigest()
        if actual_hash != stored_hash:
            context_mismatches += 1
            continue
        try:
            document = json.loads(context)
        except (UnicodeDecodeError, json.JSONDecodeError):
            context_mismatches += 1
            continue
        feature = document.get("feature") if isinstance(document, dict) else None
        bronze = document.get("bronze_pins") if isinstance(document, dict) else None
        required_bronze = {
            "snapshot_id",
            "capture_event_id",
            "envelope_hash",
            "recording_fingerprint",
            "source_label",
        }
        if (
            not isinstance(feature, dict)
            or not isinstance(bronze, dict)
            or document.get("version") != EXPECTED_FEATURE_SET
            or document.get("silver_revision_id") is None
            or document.get("silver_context_sha256") is None
            or not required_bronze.issubset(bronze)
            or feature.get("version") != EXPECTED_FEATURE_SET
            or feature.get("decision_eligibility_asserted") is not False
        ):
            lineage_mismatches += 1
        if feature.get("decision_eligibility_asserted") is not False:
            eligibility_mismatches += 1

    checks = [
        ("gold_feature_sets", feature_sets, feature_sets),
        ("gold_feature_observations", feature_sets, feature_observations),
        ("gold_feature_attempts", feature_sets, feature_attempts),
        ("gold_audit_jobs", feature_sets, audit_jobs),
        ("gold_job_events", feature_sets * 3, job_events),
        ("gold_completed_jobs", feature_sets, completed_jobs),
        ("gold_dataset_contract", 1, contracts),
        ("missing_feature_observations", 0, missing_observations),
        ("missing_feature_attempts", 0, missing_attempts),
        ("duplicate_silver_revisions", 0, duplicate_silver_revisions),
        ("invalid_context_hash", 0, invalid_context_hash),
        ("context_hash_mismatches", 0, context_mismatches),
        ("lineage_mismatches", 0, lineage_mismatches),
        ("decision_eligibility_mismatches", 0, eligibility_mismatches),
    ]

    print("Gold option-chain completeness check")
    print("===================================")
    print(f"catalog={catalog}")
    print(f"feature_set={EXPECTED_FEATURE_SET}")
    print()
    all_passed = True
    for name, expected, actual in checks:
        passed = expected == actual
        all_passed = all_passed and passed
        print(f"{'PASS' if passed else 'FAIL'} {name}: expected={expected} actual={actual}")
    print()
    print(f"RESULT: {'PASS' if all_passed else 'FAIL'}")
    return 0 if all_passed else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-db", type=Path, required=True)
    args = parser.parse_args(argv)
    conn = duckdb.connect(str(args.gold_db), read_only=True)
    try:
        return check_gold(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
