"""Shared partitioned warehouse exports; callers own the store connection."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from nse_quant.persistence.duckdb_store import DuckDBStore


def _export_path(*, export_dir: Path, underlying: str, trading_date: date, prefix: str) -> Path:
    return (
        export_dir
        / f"underlying={underlying}"
        / f"year={trading_date.year}"
        / f"month={trading_date.month:02d}"
        / f"{prefix}_{trading_date.isoformat()}.parquet"
    )


def build_option_stream_export_path(
    *,
    export_dir: Path,
    underlying: str,
    trading_date: date,
) -> Path:
    return _export_path(
        export_dir=export_dir,
        underlying=underlying,
        trading_date=trading_date,
        prefix="option_stream",
    )


def build_regime_export_path(
    *,
    export_dir: Path,
    underlying: str,
    trading_date: date,
) -> Path:
    return _export_path(
        export_dir=export_dir,
        underlying=underlying,
        trading_date=trading_date,
        prefix="market_regime",
    )


def export_option_stream(
    *,
    store: DuckDBStore,
    export_dir: Path,
    underlying: str,
    trading_date: date,
) -> int:
    """Return the CLI status: 1 for no rows, otherwise 0. Errors propagate."""
    output_path = build_option_stream_export_path(
        export_dir=export_dir,
        underlying=underlying,
        trading_date=trading_date,
    )
    row_count = store.conn.execute(
        """
        SELECT COUNT(*) FROM option_stream
        WHERE underlying = ? AND CAST(ts AS DATE) = ?
        """,
        [underlying, trading_date],
    ).fetchone()[0]
    if row_count == 0:
        print(f"No option_stream rows for {underlying} on {trading_date}")
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    escaped_path = str(output_path).replace("'", "''")
    store.conn.execute(
        f"""
        COPY (
            SELECT run_id, ts, underlying, expiry, strike, option_type,
                   tradingsymbol, instrument_token, lot_size, spot, ltp,
                   bid, ask, volume, oi, iv, delta, gamma, vega, theta,
                   quote_status, payload_json
            FROM option_stream
            WHERE underlying = ? AND CAST(ts AS DATE) = ?
            ORDER BY ts
        )
        TO '{escaped_path}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """,  # noqa: S608
        [underlying, trading_date],
    )
    print(f"Exported {row_count} rows: {output_path}")
    return 0


def export_market_regimes(
    *,
    store: DuckDBStore,
    export_dir: Path,
    underlying: str,
    start_date: date,
    end_date: date,
) -> int:
    """Export available regime days. Empty ranges retain success status."""
    rows = store.conn.execute(
        """
        SELECT CAST(ts AS DATE) AS trading_date FROM market_regimes
        WHERE symbol = ? AND CAST(ts AS DATE) BETWEEN ? AND ?
        GROUP BY 1 ORDER BY 1
        """,
        [underlying, start_date, end_date],
    ).fetchall()
    for (trading_date,) in rows:
        output_path = build_regime_export_path(
            export_dir=export_dir,
            underlying=underlying,
            trading_date=trading_date,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        store.export_market_regime_parquet(
            output_path=output_path,
            underlying=underlying,
            date_str=trading_date.isoformat(),
        )
        print(f"Exported {trading_date}: {output_path}")
    print(f"Exported regime days: {len(rows)}")
    return 0
