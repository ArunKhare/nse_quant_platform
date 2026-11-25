"""Read-only IV30 research feature commands; default planning performs no I/O."""

from __future__ import annotations

import argparse
import json
from contextlib import ExitStack
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["eod", "live"])
    parser.add_argument("--series-db", type=Path, required=True)
    parser.add_argument("--observation-id", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--trade-date")
    parser.add_argument("--max-age-calendar-days", type=int, default=4)
    parser.add_argument("--max-age-seconds", type=float, default=300)
    parser.add_argument("--bronze", type=Path)
    parser.add_argument("--vix-silver", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(dict(status="PLANNED_NO_IO", kind=args.kind, decision_eligibility_asserted=False)))
        return 0
    if args.kind == "eod" and (not args.trade_date or args.bronze or args.vix_silver):
        raise ValueError("S2_EXPLICIT_EOD_DATE_AND_NO_LIVE_SUBSTITUTION_REQUIRED")
    if args.kind == "live" and (not args.bronze or not args.vix_silver or args.trade_date):
        raise ValueError("S2_EXPLICIT_LIVE_SOURCES_AND_NO_EOD_SUBSTITUTION_REQUIRED")
    import duckdb

    from nse_quant.analytics.s2_iv30_features import sha
    from nse_quant.data_platform import s2_iv30_feature_reader as reader
    from nse_quant.data_platform.s2_series_cli import _write_new

    with ExitStack() as stack:

        def opened(path: Path):
            if not path.is_file():
                raise ValueError("S2_EXISTING_FEATURE_SOURCE_REQUIRED")
            return stack.enter_context(duckdb.connect(str(path), read_only=True))

        store = opened(args.series_db)
        common = dict(observation_id=args.observation_id, expected_sha256=args.expected_sha256, as_of=args.as_of)
        if args.kind == "eod":
            raw = reader.read_eod_feature(
                store, **common, trade_date=args.trade_date, max_age_calendar_days=args.max_age_calendar_days
            )
        else:
            raw = reader.read_live_feature(
                store, opened(args.bronze), opened(args.vix_silver), **common, max_age_seconds=args.max_age_seconds
            )
    _write_new(args.output, raw)
    print(
        json.dumps(dict(status="RESEARCH_FEATURE_NOT_PUBLISHED", digest=sha(raw), decision_eligibility_asserted=False))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
