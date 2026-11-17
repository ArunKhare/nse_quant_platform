"""Read-only status/query CLI for persisted native decision reconciliations.

Inspects and exactly replays a persisted reconciliation with authoritative
identity/time evidence. Returns an observational result only. No eligibility,
live trading, healing, backfill, adoption, or execution authority.
POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from nse_quant.data_platform.native_iron_condor_decision_reconciliation_boundary import (
    replay_reconciliation_with_authoritative_boundary,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-iron-condor-decision-loop-status-cli@1"
COMMAND = "native-iron-condor-decision-loop-status"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=COMMAND)
    parser.add_argument("--reconciliation-database", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--revision-id", required=True)
    parser.add_argument("--recording-fingerprint", required=True)
    return parser


def run_cli(argv: list[str] | None = None) -> dict[str, Any]:
    """Inspect and exactly replay a persisted reconciliation."""
    parser = build_parser()
    args = parser.parse_args(argv)
    database_path = Path(args.reconciliation_database)
    if not database_path.is_file():
        raise Rejected("RECONCILIATION_DATABASE_REQUIRED")
    import duckdb

    with duckdb.connect(str(database_path)) as target:
        return replay_reconciliation_with_authoritative_boundary(
            target,
            run_id=args.run_id,
            expected_revision_id=args.revision_id,
            expected_recording_fingerprint=args.recording_fingerprint,
        )


def main(argv: list[str] | None = None) -> int:
    try:
        result = run_cli(argv)
    except Rejected as error:
        print(json.dumps({"rejected": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0
