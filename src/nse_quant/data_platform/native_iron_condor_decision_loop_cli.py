"""Read-only CLI for the native iron-condor decision-loop integration.

Exposes the existing decision-loop integration through a narrowly scoped
command-line entry point. Reads JSON request, coverage, and authoritative
boundary documents; runs, reconciles, persists, and replays the decision run;
and prints a JSON observational result. No eligibility, live trading, healing,
backfill, adoption, or execution authority. POINT_IN_TIME_DECISION remains
rejected.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from nse_quant.data_platform.native_iron_condor_decision_loop_integration import (
    run_native_iron_condor_decision_loop,
)
from nse_quant.data_platform.native_iron_condor_decision_run_orchestrator import (
    NativeDecisionRunRequest,
)
from nse_quant.data_platform.native_iron_condor_portfolio_risk_decision import (
    NativePortfolioRiskDecisionInputBundle,
    PortfolioRiskSettings,
)
from nse_quant.data_platform.native_iron_condor_strategy_decision import (
    NativeStrategyDecisionInputBundle,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-iron-condor-decision-loop-cli@1"
COMMAND = "native-iron-condor-decision-loop"


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise Rejected(f"{label}_FILE_REQUIRED")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Rejected(f"{label}_JSON_INVALID") from error
    if type(value) is not dict:
        raise Rejected(f"{label}_DOCUMENT_REQUIRED")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=COMMAND)
    parser.add_argument("--decision-database", required=True)
    parser.add_argument("--reconciliation-database", required=True)
    parser.add_argument("--request-json", required=True)
    parser.add_argument("--coverage-json", required=True)
    parser.add_argument("--boundary-json", required=True)
    return parser


def run_cli(argv: list[str] | None = None) -> dict[str, Any]:
    """Run the read-only native decision-loop CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    decision_path = Path(args.decision_database)
    reconciliation_path = Path(args.reconciliation_database)
    request_document = _load_json(Path(args.request_json), "REQUEST")
    coverage = _load_json(Path(args.coverage_json), "COVERAGE")
    boundary = _load_json(Path(args.boundary_json), "BOUNDARY")

    import duckdb

    with (
        duckdb.connect(str(decision_path)) as decision_target,
        duckdb.connect(str(reconciliation_path)) as reconciliation_target,
    ):
        result = run_native_iron_condor_decision_loop(
            decision_target,
            reconciliation_target,
            request=NativeDecisionRunRequest(
                run_id=request_document["run_id"],
                actor_id=request_document["actor_id"],
                code_revision=request_document["code_revision"],
                strategy_bundle=NativeStrategyDecisionInputBundle(**request_document["strategy_bundle"]),
                portfolio_risk_bundle=NativePortfolioRiskDecisionInputBundle(
                    **{
                        **request_document["portfolio_risk_bundle"],
                        "settings": PortfolioRiskSettings(**request_document["portfolio_risk_bundle"]["settings"]),
                    }
                ),
            ),
            coverage_report=coverage,
            authoritative_boundary=boundary,
        )
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        result = run_cli(argv)
    except Rejected as error:
        print(json.dumps({"rejected": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0
