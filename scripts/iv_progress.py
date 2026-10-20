"""Report IV-history and IV-RV alignment progress."""

from __future__ import annotations

from datetime import UTC, datetime

from nse_quant.features.availability_checker import (
    FeatureAvailabilityChecker,
)
from nse_quant.persistence.duckdb_store import DuckDBStore


def main() -> int:
    store = DuckDBStore()
    checker = FeatureAvailabilityChecker(store)

    report = checker.evaluate(
        symbol="NIFTY",
        instrument_token=256265,
        as_of=datetime.now(UTC),
    )

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