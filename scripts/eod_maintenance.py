"""Automated end-of-day maintenance for the NSE Quant platform.

Builds daily and intraday candles, daily realized volatility,
exports research data to Parquet, and sends an operational summary.
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

DEFAULT_CANDLE_INTERVALS = "5m,15m,30m,60m"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run end-of-day maintenance",
    )

    parser.add_argument(
        "--symbol",
        default=None,
        help="Underlying symbol; defaults to configured default symbol",
    )

    parser.add_argument(
        "--instrument-token",
        type=int,
        default=None,
        help=(
            "Spot instrument token. Defaults to "
            "settings.market_data.default_instrument_token when available."
        ),
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
        "--candle-intervals",
        default=DEFAULT_CANDLE_INTERVALS,
        help=("Comma-separated intraday candle intervals to build; default: 5m,15m,30m,60m"),
    )

    parser.add_argument(
        "--config",
        default=None,
        help="Optional settings YAML path",
    )

    parser.add_argument(
        "--skip-export",
        action="store_true",
        help="Skip Parquet warehouse exports",
    )

    return parser.parse_args()


def build_export_path(
    *,
    export_dir: Path,
    underlying: str,
    trading_date: date,
    dataset: str,
) -> Path:
    return (
        export_dir
        / f"underlying={underlying}"
        / f"year={trading_date.year}"
        / f"month={trading_date.month:02d}"
        / f"{dataset}_{trading_date.isoformat()}.parquet"
    )


def run_command(command: list[str]) -> None:
    print(f"Running: {' '.join(command)}")

    completed = subprocess.run(
        command,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {completed.returncode}: {' '.join(command)}",
        )


def export_query_to_parquet(
    *,
    store: DuckDBStore,
    query: str,
    parameters: list[object],
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        output_path.unlink()

    escaped_path = str(output_path).replace("'", "''")

    store.conn.execute(
        f"""
        COPY ({query})
        TO '{escaped_path}'
        (FORMAT PARQUET, COMPRESSION ZSTD)
        """,
        parameters,
    )

    return output_path


def export_spot_candles(
    *,
    store: DuckDBStore,
    symbol: str,
    trade_date: str,
    intervals: list[str],
    output_path: Path,
) -> Path:
    placeholders = ", ".join("?" for _ in intervals)

    query = f"""
        SELECT
            symbol,
            instrument_token,
            ts,
            interval,
            open,
            high,
            low,
            close,
            volume,
            oi
        FROM spot_candles
        WHERE symbol = ?
          AND CAST(ts AS DATE) = ?
          AND interval IN ({placeholders})
        ORDER BY interval, ts
    """

    parameters: list[object] = [symbol, trade_date, *intervals]

    return export_query_to_parquet(
        store=store,
        query=query,
        parameters=parameters,
        output_path=output_path,
    )


def export_daily_rv(
    *,
    store: DuckDBStore,
    symbol: str,
    trade_date: str,
    output_path: Path,
) -> Path:
    query = """
        SELECT
            symbol,
            trading_date,
            rv,
            observation_count
        FROM daily_rv_observations
        WHERE symbol = ?
          AND CAST(trading_date AS DATE) = ?
        ORDER BY trading_date
    """

    return export_query_to_parquet(
        store=store,
        query=query,
        parameters=[symbol, trade_date],
        output_path=output_path,
    )


def get_observation_counts(
    *,
    store: DuckDBStore,
    symbol: str,
    trade_date: str,
) -> dict[str, int]:
    interval_counts = store.conn.execute(
        """
        SELECT
            interval,
            COUNT(*) AS candle_count
        FROM spot_candles
        WHERE symbol = ?
          AND CAST(ts AS DATE) = ?
        GROUP BY interval
        ORDER BY interval
        """,
        [symbol, trade_date],
    ).fetchall()

    iv_observations = store.count_underlying_iv_observations(
        underlying=symbol,
    )

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

    counts = {
        "iv_observations": int(iv_observations),
        "iv_rv_aligned_days": int(aligned),
    }

    for interval, candle_count in interval_counts:
        counts[f"candles_{interval}"] = int(candle_count)

    return counts


def get_option_stream_count_for_date(
    *,
    store: DuckDBStore,
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
    exported_files: list[Path],
    validation_issues: list[str] | None = None,
) -> str:
    lines = [
        "NSE Quant EOD summary",
        f"Symbol: {symbol}",
        f"Trade date: {trade_date}",
        f"IV observations: {counts.get('iv_observations', 0):,}",
        (f"IV-RV aligned days: {counts.get('iv_rv_aligned_days', 0):,}/30"),
    ]

    for name, value in counts.items():
        if name.startswith("candles_"):
            lines.append(f"{name}: {value:,}")

    if exported_files:
        lines.append("Warehouse exports:")
        lines.extend(f"  - {path}" for path in exported_files)

    if validation_issues:
        lines.append(
            "Warehouse validation: FAILED — " + ", ".join(validation_issues),
        )

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    settings = get_settings(args.config)

    export_dir = args.export_dir
    symbol = args.symbol or settings.market_data.default_symbol

    trade_date = args.trade_date or datetime.now(UTC).astimezone(IST).date().isoformat()

    trade_day = date.fromisoformat(trade_date)

    notifier = Notifier() if settings.notifier.enabled else NullNotifier()

    if not is_nse_trading_day(trade_day):
        message = f"NSE Quant EOD skipped: market holiday ({trade_date})."

        print(message)
        notifier.send(message)
        return 0

    instrument_token = args.instrument_token

    if instrument_token is None:
        instrument_token = getattr(
            settings.market_data,
            "default_instrument_token",
            None,
        )

    if instrument_token is None:
        message = (
            "NSE Quant EOD failed: no instrument token supplied and "
            "no default_instrument_token configured."
        )

        print(message)
        notifier.send(message)
        return 1

    candle_intervals = [
        value.strip() for value in args.candle_intervals.split(",") if value.strip()
    ]

    exported_files: list[Path] = []
    validation_issues: list[str] = []

    try:
        run_command(
            [
                sys.executable,
                "scripts/build_daily_rv.py",
                "--symbol",
                symbol,
                "--instrument-token",
                str(instrument_token),
            ],
        )

        run_command(
            [
                sys.executable,
                "scripts/build_daily_candles.py",
                "--symbol",
                symbol,
                "--start-date",
                trade_date,
                "--end-date",
                trade_date,
            ],
        )

        if candle_intervals:
            run_command(
                [
                    sys.executable,
                    "scripts/build_interval_candles.py",
                    "--symbol",
                    symbol,
                    "--trade-date",
                    trade_date,
                    "--intervals",
                    ",".join(candle_intervals),
                ],
            )

        store = DuckDBStore()

        try:
            counts = get_observation_counts(
                store=store,
                symbol=symbol,
                trade_date=trade_date,
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
                    exported_files=[],
                    validation_issues=[
                        "no_option_stream_observations_for_trade_date",
                    ],
                )

                print(summary)
                notifier.send(summary)
                return 0

            if not args.skip_export:
                option_stream_path = build_export_path(
                    export_dir=export_dir,
                    underlying=symbol,
                    trading_date=trade_day,
                    dataset="option_stream",
                )

                option_stream_path = store.export_parquet(
                    output_path=option_stream_path,
                    underlying=symbol,
                    date_str=trade_date,
                )

                exported_files.append(option_stream_path)

                validation = validate_parquet_file(
                    option_stream_path,
                    underlying=symbol,
                )

                if validation["status"] != "ok":
                    validation_issues.extend(
                        validation.get("issues", []),
                    )

                regime_path = build_export_path(
                    export_dir=export_dir,
                    underlying=symbol,
                    trading_date=trade_day,
                    dataset="market_regime",
                )

                regime_path = store.export_market_regime_parquet(
                    output_path=regime_path,
                    underlying=symbol,
                    date_str=trade_date,
                )

                exported_files.append(regime_path)

                candles_path = build_export_path(
                    export_dir=export_dir,
                    underlying=symbol,
                    trading_date=trade_day,
                    dataset="spot_candles",
                )

                candles_path = export_spot_candles(
                    store=store,
                    symbol=symbol,
                    trade_date=trade_date,
                    intervals=["1m", "day", *candle_intervals],
                    output_path=candles_path,
                )

                exported_files.append(candles_path)

                rv_path = build_export_path(
                    export_dir=export_dir,
                    underlying=symbol,
                    trading_date=trade_day,
                    dataset="daily_rv",
                )

                rv_path = export_daily_rv(
                    store=store,
                    symbol=symbol,
                    trade_date=trade_date,
                    output_path=rv_path,
                )

                exported_files.append(rv_path)

            summary = build_summary(
                symbol=symbol,
                trade_date=trade_date,
                counts=counts,
                exported_files=exported_files,
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
