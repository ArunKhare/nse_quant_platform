"""Automated end-of-day maintenance for the NSE Quant platform.

Builds daily realized volatility, exports the day's option stream,
and sends an operational Telegram summary.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from nse_quant.core.settings import get_settings
from nse_quant.ops.notifier import Notifier, NullNotifier
from nse_quant.persistence.duckdb_store import DuckDBStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run end-of-day maintenance"
    )

    parser.add_argument(
        "--symbol",
        default=None,
        help="Underlying symbol; defaults to configured default symbol",
    )

    parser.add_argument(
        "--instrument-token",
        type=int,
        required=True,
        help="Spot instrument token used for daily RV construction",
    )

    parser.add_argument(
        "--trade-date",
        default=None,
        help="Trade date in YYYY-MM-DD format; defaults to today in IST",
    )

    parser.add_argument(
        "--export-dir",
        default="data/exports",
        help="Directory for daily Parquet exports",
    )

    parser.add_argument(
        "--config",
        default=None,
        help="Optional settings YAML path",
    )

    parser.add_argument(
        "--skip-export",
        action="store_true",
        help="Skip Parquet export",
    )

    return parser.parse_args()


def run_command(command: list[str]) -> None:
    print(f"Running: {' '.join(command)}")

    completed = subprocess.run(
        command,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {completed.returncode}: "
            f"{' '.join(command)}"
        )


def get_observation_counts(
    store: DuckDBStore,
    symbol: str,
) -> dict[str, int]:
    one_minute = store.conn.execute(
        """
        SELECT COUNT(*)
        FROM spot_candles
        WHERE symbol = ?
          AND interval = '1m'
        """,
        [symbol],
    ).fetchone()[0]

    iv_observations = store.count_underlying_iv_observations(
        underlying=symbol
    )

    aligned = store.conn.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT DISTINCT CAST(iv.ts AS DATE) AS trade_date
            FROM underlying_iv_observations iv
            INNER JOIN daily_rv_observations  rv
                ON rv.symbol = ?
                AND CAST(rv.trading_date AS DATE) = CAST(iv.ts AS DATE)
            WHERE iv.underlying = ?
        )
        """,
        [symbol, symbol],
    ).fetchone()[0]

    return {
        "candles_1m": int(one_minute),
        "iv_observations": int(iv_observations),
        "iv_rv_aligned_days": int(aligned),
    }


def build_summary(
    *,
    symbol: str,
    trade_date: str,
    counts: dict[str, int],
    parquet_path: Path | None,
) -> str:
    lines = [
        "NSE Quant EOD summary",
        f"Symbol: {symbol}",
        f"Trade date: {trade_date}",
        f"1m candles: {counts['candles_1m']:,}",
        f"IV observations: {counts['iv_observations']:,}",
        (
            "IV-RV aligned days: "
            f"{counts['iv_rv_aligned_days']:,}/30"
        ),
    ]

    if parquet_path is not None:
        lines.append(f"Parquet export: {parquet_path}")

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    settings = get_settings(args.config)

    export_dir = args.export_dir or settings.storage.parquet_dir
    symbol = args.symbol or settings.market_data.default_symbol

    trade_date = (
        args.trade_date
        or datetime.now(UTC).astimezone(
            settings.market_data.ist_timezone
        ).date().isoformat()
    )

    notifier = (
        Notifier()
        if settings.notifier.enabled
        else NullNotifier()
    )

    try:
        run_command(
            [
                sys.executable,
                "scripts/build_daily_rv.py",
                "--symbol",
                symbol,
                "--instrument-token",
                str(args.instrument_token),
            ]
        )

        store = DuckDBStore()

        try:
            counts = get_observation_counts(
                store=store,
                symbol=symbol,
            )

            parquet_path: Path | None = None

            if not args.skip_export:
                parquet_path = store.export_parquet(
                    output_dir=export_dir,
                    date_str=trade_date,
                )

            summary = build_summary(
                symbol=symbol,
                trade_date=trade_date,
                counts=counts,
                parquet_path=parquet_path,
            )

            print(summary)
            notifier.send(summary)

        finally:
            store.conn.close()

    except Exception as exc:  # noqa: BLE001
        message = f"NSE Quant EOD maintenance failed: {exc}"
        print(message)
        notifier.send(message)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())