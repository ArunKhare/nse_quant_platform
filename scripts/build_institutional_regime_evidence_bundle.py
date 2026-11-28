"""Build a pinned institutional-regime research evidence bundle from decision_evidence.

Run only when the decisions database is quiescent or against an immutable copy.
The command opens the database read-only and writes research artifacts outside
the operational store.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from nse_quant.research.institutional_regime_evidence import (
    build_institutional_regime_evidence_bundle,
    load_institutional_regime_observations,
    write_institutional_regime_evidence_bundle,
)


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assemble a research-only institutional regime evidence bundle."
    )
    parser.add_argument("--db-path", required=True, type=Path, help="Quiescent decisions DuckDB or immutable copy.")
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--start", required=True, type=_timestamp, help="Inclusive ISO-8601 UTC timestamp.")
    parser.add_argument("--end", required=True, type=_timestamp, help="Exclusive ISO-8601 UTC timestamp.")
    parser.add_argument("--output", required=True, type=Path, help="JSON bundle output path.")
    parser.add_argument("--markdown-output", type=Path, help="Review report path; defaults to output with .md.")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not args.db_path.is_file():
        raise FileNotFoundError(args.db_path)
    if args.end <= args.start:
        raise ValueError("--end must be later than --start")

    connection = duckdb.connect(str(args.db_path), read_only=True)
    try:
        connection.execute("SET TimeZone = 'UTC'")
        observations = load_institutional_regime_observations(
            connection,
            symbol=args.symbol,
            start=args.start,
            end=args.end,
        )
    finally:
        connection.close()

    bundle = build_institutional_regime_evidence_bundle(
        observations,
        symbol=args.symbol,
        start=args.start,
        end=args.end,
    )
    markdown_path = args.markdown_output or args.output.with_suffix(".md")
    write_institutional_regime_evidence_bundle(
        bundle,
        json_path=args.output,
        markdown_path=markdown_path,
    )
    print(f"bundle_id={bundle['bundle_id']}")
    print(f"evidence_records={bundle['summary']['observation_count']}")
    print(f"complete_regimes={bundle['summary']['canonical_label_count']}")
    print(f"review_status={bundle['review']['review_status']}")
    print(f"json_bundle={args.output}")
    print(f"review_report={markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
