"""Bounded read-only query for persisted native decision reconciliations.

Returns a bounded list of reconciliation summaries from a dedicated
reconciliation Silver database. This is observational only: no eligibility,
live trading, healing, backfill, adoption, or execution authority.
POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from nse_quant.data_platform.audited_decision_reconciliation_silver import (
    _schema,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-iron-condor-decision-reconciliation-query@1"
COMMAND = "query.native_iron_condor_decision_reconciliations@1"
MAX_LIMIT = 100


def _validate_limit(limit: int) -> int:
    if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
        raise Rejected("RECONCILIATION_QUERY_LIMIT_INVALID")
    return limit


def query_native_iron_condor_decision_reconciliations(
    target: Any,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return a bounded list of persisted reconciliation summaries."""
    limit = _validate_limit(limit)
    _schema(target)
    sets = "silver.audited_decision_reconciliation_sets"
    observations = "silver.audited_decision_reconciliation_observations"
    rows = target.execute(
        f"""
        SELECT s.run_id, s.revision_id, s.coverage_revision_id,
               s.coverage_recording_fingerprint, s.recorded_at,
               o.record_bytes
        FROM {sets} AS s
        JOIN {observations} AS o
          ON o.revision_id = s.revision_id
        ORDER BY s.recorded_at DESC, s.revision_id DESC
        LIMIT ?
        """,
        [limit],
    ).fetchall()
    summaries: list[dict[str, Any]] = []
    for run_id, revision_id, coverage_revision_id, fingerprint, recorded_at, record_bytes in rows:
        document = json.loads(bytes(record_bytes).decode("utf-8"))
        boundary = document.get("authoritative_boundary")
        summaries.append(
            {
                "run_id": run_id,
                "revision_id": revision_id,
                "coverage_revision_id": coverage_revision_id,
                "coverage_recording_fingerprint": fingerprint,
                "recorded_at": recorded_at.isoformat(),
                "authoritative_boundary_present": type(boundary) is dict,
                "decision_eligibility_asserted": False,
            }
        )
    return summaries


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=COMMAND)
    parser.add_argument("--reconciliation-database", required=True)
    parser.add_argument("--limit", type=int, default=20)
    return parser


def run_cli(argv: list[str] | None = None) -> list[dict[str, Any]]:
    """Run the bounded read-only reconciliation query CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    database_path = Path(args.reconciliation_database)
    if not database_path.is_file():
        raise Rejected("RECONCILIATION_DATABASE_REQUIRED")
    import duckdb

    with duckdb.connect(str(database_path)) as target:
        return query_native_iron_condor_decision_reconciliations(
            target,
            limit=args.limit,
        )


def main(argv: list[str] | None = None) -> int:
    try:
        summaries = run_cli(argv)
    except Rejected as error:
        print(json.dumps({"rejected": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(summaries, sort_keys=True, separators=(",", ":")))
    return 0
