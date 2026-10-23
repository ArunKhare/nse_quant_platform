"""Classify daily IV regimes from IV surface research data."""

from __future__ import annotations

import argparse

from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.iv_regimes import (
    classify_iv_regimes,
    save_regime_report,
)
from nse_quant.research.iv_surface import (
    build_daily_iv_summary,
    build_iv_surface_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify daily IV regimes")

    parser.add_argument(
        "--underlying",
        default="NIFTY",
    )

    parser.add_argument(
        "--from",
        dest="from_date",
        required=True,
        help="Start date, YYYY-MM-DD",
    )

    parser.add_argument(
        "--to",
        dest="to_date",
        required=True,
        help="End date, YYYY-MM-DD",
    )

    parser.add_argument(
        "--output-dir",
        default="data/research",
    )

    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist daily IV regimes to market_regimes",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    store = DuckDBStore()

    try:
        frame = store.conn.execute(
            """
            SELECT
                ts,
                underlying,
                expiry,
                strike,
                option_type,
                ltp,
                spot,
                iv,
                delta
            FROM option_stream
            WHERE underlying = ?
              AND CAST(ts AS DATE) BETWEEN ? AND ?
              AND iv IS NOT NULL
              AND delta IS NOT NULL
            ORDER BY ts
            """,
            [args.underlying, args.from_date, args.to_date],
        ).fetchdf()

        if frame.empty:
            print("No eligible option-stream data found.")
            return 1

        snapshot_report = build_iv_surface_report(
            frame,
            underlying=args.underlying,
        )

        if snapshot_report.empty:
            print("Not enough multi-expiry snapshots to classify IV regimes.")
            return 1

        daily_report = build_daily_iv_summary(snapshot_report)

        regime_report = classify_iv_regimes(daily_report)

        if args.persist:
            persisted = 0

            for _, row in regime_report.iterrows():
                persisted += store.write_daily_iv_regime(
                    trade_date=row["trade_date"],
                    underlying=args.underlying,
                    iv_level=row["iv_level"],
                    iv_term_regime=row["iv_term_regime"],
                    iv_skew_regime=row["iv_skew_regime"],
                    iv_regime=row["iv_regime"],
                    metrics={
                        "median_spot": float(row["median_spot"]),
                        "median_atm_iv_near": float(row["median_atm_iv_near"]),
                        "median_atm_iv_next": float(row["median_atm_iv_next"]),
                        "median_term_structure": float(row["median_term_structure"]),
                        "median_put_call_skew": float(row["median_put_call_skew"]),
                        "median_risk_reversal": float(row["median_risk_reversal"]),
                        "median_butterfly": float(row["median_butterfly"]),
                    },
                )

            print(f"Persisted IV regimes: {persisted}")
        output_path = save_regime_report(
            regime_report,
            output_dir=args.output_dir,
            underlying=args.underlying,
        )

        print(
            {
                "days": len(regime_report),
                "regimes": (regime_report["iv_regime"].value_counts().to_dict()),
                "report": str(output_path),
            }
        )

        return 0

    finally:
        store.conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
