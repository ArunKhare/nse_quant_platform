from __future__ import annotations

import argparse
import json
from pathlib import Path

from nse_quant.research.paper_loop_vrp_readiness import (
    build_paper_loop_vrp_readiness_report,
    load_paper_loop_payload,
    render_paper_loop_vrp_readiness_markdown,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a read-only paper-loop and VRP readiness report from a saved loop result."
    )
    parser.add_argument("--input", required=True, help="Path to logs/paper_loop_last_decision.json")
    parser.add_argument("--output", default="logs/paper_loop_vrp_readiness.md")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = load_paper_loop_payload(args.input)
    report = build_paper_loop_vrp_readiness_report(payload)
    output = (
        render_paper_loop_vrp_readiness_markdown(report)
        if args.format == "markdown"
        else json.dumps(report, indent=2, default=str) + "\n"
    )
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(output, encoding="utf-8")
    print(f"Readiness report written: {destination}")
    print(f"Overall status: {report['overall_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
