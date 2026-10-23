"""Automated end-of-day maintenance for the NSE Quant platform.

Builds daily realized volatility, exports the day's option stream,
and sends an operational Telegram summary.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from nse_quant.core.market_calendar import is_nse_trading_day
from nse_quant.core.settings import get_settings
from nse_quant.ops.notifier import Notifier, NullNotifier
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.warehouse_validation import (
    validate_parquet_file,
)

IST = ZoneInfo("Asia/Kolkata")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run end-of-day maintenance")

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
        type=Path,
        default=Path("data/exports"),
        help="Base directory for daily Parquet exports",
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


def build_export_path(
    *,
    export_dir: Path,
    underlying: str,
    trading_date: date,
) -> Path:
    """Build the Hive-partitioned Parquet warehouse path."""

    return (
        export_dir
        / f"underlying={underlying}"
        / f"year={trading_date.year}"
        / f"month={trading_date.month:02d}"
        / f"option_stream_{trading_date.isoformat()}.parquet"
    )


def run_command(command: list[str]) -> None:
    print(f"Running: {' '.join(command)}")

    completed = subprocess.run(
        command,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {completed.returncode}: {' '.join(command)}"
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

    iv_observations = store.count_underlying_iv_observations(underlying=symbol)

    aligned = store.conn.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT DISTINCT CAST(iv.ts AS DATE) AS trade_date
            FROM underlying_iv_observations iv
            INNER JOIN daily_rv_observations rv
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


def get_option_stream_count_for_date(
    store: DuckDBStore,
    *,
    underlying: str,
    trading_date: date,
) -> int:
    count = store.conn.execute(
        """
        SELECT COUNT(*)
        FROM option_stream
        WHERE underlying = ?
          AND CAST(ts AS DATE) = ?
        """,
        [underlying, trading_date],
    ).fetchone()[0]

    return int(count)


def build_summary(
    *,
    symbol: str,
    trade_date: str,
    counts: dict[str, int],
    parquet_path: Path | None,
    regime_path: Path | None,
    validation_issues: list[str] | None = None,
) -> str:
    lines = [
        "NSE Quant EOD summary",
        f"Symbol: {symbol}",
        f"Trade date: {trade_date}",
        f"1m candles: {counts['candles_1m']:,}",
        f"IV observations: {counts['iv_observations']:,}",
        (f"IV-RV aligned days: {counts['iv_rv_aligned_days']:,}/30"),
    ]

    if parquet_path is not None:
        lines.append(f"Parquet export: {parquet_path}")

    if validation_issues:
        lines.append("Warehouse validation: FAILED — " + ", ".join(validation_issues))
    if regime_path is not None:
        lines.append(f"Regime export: {regime_path}")
    return "\n".join(lines)


def build_regime_export_path(
    *,
    export_dir: Path,
    underlying: str,
    trading_date: date,
) -> Path:
    return (
        export_dir
        / f"underlying={underlying}"
        / f"year={trading_date.year}"
        / f"month={trading_date.month:02d}"
        / f"market_regime_{trading_date.isoformat()}.parquet"
    )


def main() -> int:
    args = parse_args()
    settings = get_settings(args.config)

    export_dir = args.export_dir
    symbol = args.symbol or settings.market_data.default_symbol

    trade_date = args.trade_date or datetime.now(UTC).astimezone(IST).date().isoformat()

    notifier = Notifier() if settings.notifier.enabled else NullNotifier()

    trade_day = date.fromisoformat(trade_date)

    if not is_nse_trading_day(trade_day):
        message = f"NSE Quant EOD skipped: market holiday ({trade_date})."

        print(message)
        notifier.send(message)
        return 0

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
            option_stream_count = get_option_stream_count_for_date(
                store=store,
                underlying=symbol,
                trading_date=trade_day,
            )

            if option_stream_count == 0:
                message = (
                    "NSE Quant EOD skipped export: no option-stream "
                    f"observations for {symbol} on {trade_date}."
                )

                print(message)
                notifier.send(message)

                summary = build_summary(
                    symbol=symbol,
                    trade_date=trade_date,
                    counts=counts,
                    parquet_path=None,
                    regime_path=None,
                    validation_issues=["no_option_stream_observations_for_trade_date"],
                )

                print(summary)
                notifier.send(summary)

                return 0

            parquet_path: Path | None = None
            validation_issues: list[str] = []

            if not args.skip_export:
                output_path = build_export_path(
                    export_dir=export_dir,
                    underlying=symbol,
                    trading_date=trade_day,
                )

                output_path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                parquet_path = store.export_parquet(
                    output_path=output_path,
                    underlying=symbol,
                    date_str=trade_date,
                )

            if parquet_path is not None:
                validation = validate_parquet_file(
                    parquet_path,
                    underlying=symbol,
                )

                if validation["status"] != "ok":
                    validation_issues = list(validation.get("issues", []))

            regime_path: Path | None = None

            if not args.skip_export:
                regime_path = build_regime_export_path(
                    export_dir=export_dir,
                    underlying=symbol,
                    trading_date=trade_day,
                )

                regime_path.parent.mkdir(parents=True, exist_ok=True)

                store.export_market_regime_parquet(
                    output_path=regime_path,
                    underlying=symbol,
                    date_str=trade_date,
                )

            summary = build_summary(
                symbol=symbol,
                trade_date=trade_date,
                counts=counts,
                parquet_path=parquet_path,
                regime_path=regime_path,
                validation_issues=validation_issues,
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
