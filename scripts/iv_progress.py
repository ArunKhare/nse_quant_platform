"""Report IV-history and IV-RV alignment progress."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from nse_quant.core.settings import get_settings
from nse_quant.features.availability_checker import (
    FeatureAvailabilityChecker,
)
from nse_quant.persistence.duckdb_store import DuckDBStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report IV-history and feature availability",
    )
    parser.add_argument(
        "--config",
        default=None,
    )
    parser.add_argument(
        "--symbol",
        default=None,
    )
    parser.add_argument(
        "--spot-token",
        type=int,
        default=None,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings(args.config)

    symbol = args.symbol or settings.market_data.default_symbol
    spot_token = args.spot_token

    if spot_token is None:
        token = settings.market_data.index_instrument_tokens.get(symbol)
        spot_token = token

    if spot_token is None:
        raise SystemExit(f"No spot instrument token configured for {symbol}; pass --spot-token")

    store = DuckDBStore(read_only=True)
    checker = FeatureAvailabilityChecker(store)

    report = checker.evaluate(
        symbol=symbol,
        instrument_token=spot_token,
        as_of=datetime.now(UTC),
    )

    print("Symbol:", symbol)
    print("IV status:", report.iv_status.value)
    print("Overall status:", report.overall_status.value)
    print("Observations:", report.observations)
    print("Reasons:")

    for reason in report.reasons:
        print("-", reason)

    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
