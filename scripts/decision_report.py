"""Generate a decision-quality report from persisted platform events."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from nse_quant.analytics.decision_analytics import DecisionAnalyticsRepository
from nse_quant.persistence.duckdb_store import DuckDBStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a decision-quality report"
    )

    parser.add_argument("--run-id", default=None)
    parser.add_argument("--from", dest="from_ts", default=None)
    parser.add_argument("--to", dest="to_ts", default=None)
    parser.add_argument(
        "--output",
        default="data/reports/decision_report.json",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    from_ts = (
        datetime.fromisoformat(args.from_ts) if args.from_ts else None
    )
    to_ts = datetime.fromisoformat(args.to_ts) if args.to_ts else None

    store = DuckDBStore(read_only=True)
    repository = DecisionAnalyticsRepository(store=store)

    try:
        report = {
            "generated_at": datetime.now().isoformat(),
            "run_id": args.run_id,
            "feature_gate_summary": repository.feature_gate_summary(
                run_id=args.run_id,
                from_ts=from_ts,
                to_ts=to_ts,
            ).to_dict(orient="records"),
            "rejection_reasons": repository.rejection_reasons(
                run_id=args.run_id,
                from_ts=from_ts,
                to_ts=to_ts,
            ).to_dict(orient="records"),
            "funnel": repository.funnel(
                run_id=args.run_id,
                from_ts=from_ts,
                to_ts=to_ts,
            ).to_dict(orient="records"),
        }

        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, default=str),
            encoding="utf-8",
        )

        print(f"Decision report written: {output}")
    finally:
        store.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())