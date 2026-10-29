from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.backtest_readiness import (
    evaluate_backtest_readiness,
)
from scripts.eod_maintenance import build_export_path, get_option_stream_count_for_date


def test_regime_export_path_uses_hive_partitions():
    path = build_export_path(
        export_dir=Path("data/exports"),
        underlying="NIFTY",
        trading_date=date(2026, 10, 21),
        dataset="market_regime",
    )

    assert path == Path(
        "data/exports/underlying=NIFTY/year=2026/month=10/market_regime_2026-10-21.parquet"
    )


def test_build_export_path_uses_hive_partitions():
    path = build_export_path(
        export_dir=Path("data/exports"),
        underlying="NIFTY",
        trading_date=date(2026, 10, 28),
        dataset="option_stream",
    )

    assert path == Path(
        "data/exports/underlying=NIFTY/year=2026/month=10/option_stream_2026-10-28.parquet"
    )


def write_option_parquet(
    path: Path,
    trading_dates: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    frames = []

    for trading_date in trading_dates:
        frames.append(
            pd.DataFrame(
                [
                    {
                        "ts": pd.Timestamp(
                            f"{trading_date} 09:20:00",
                            tz="UTC",
                        ),
                        "underlying": "NIFTY",
                        "iv": 15.0,
                    }
                ]
            )
        )

    df = pd.concat(frames, ignore_index=True)

    conn = duckdb.connect()
    try:
        conn.register("option_rows", df)
        conn.execute(
            f"""
            COPY option_rows
            TO '{path.as_posix()}'
            (FORMAT PARQUET)
            """
        )
    finally:
        conn.close()


def test_empty_warehouse_is_not_ready(tmp_path):
    parquet_path = tmp_path / "missing_parquet.parquet"
    regime_path = tmp_path / "missing_regimes_*.parquet"
    report = evaluate_backtest_readiness(
        warehouse_glob=str(parquet_path),
        regime_glob=str(regime_path),
        underlying="NIFTY",
        min_complete_days=1,
        min_iv_rv_aligned_days=1,
        min_regime_days=1,
    )

    assert report.ready is False
    assert report.complete_option_days == 0
    assert any(blocker.startswith("warehouse_empty:") for blocker in report.blockers)


def test_not_ready_with_insufficient_days(tmp_path):
    parquet_path = tmp_path / "option_stream.parquet"
    regime_path = tmp_path / "missing_regimes_*.parquet"
    write_option_parquet(parquet_path, ["2026-10-01"])

    report = evaluate_backtest_readiness(
        warehouse_glob=str(parquet_path),
        regime_glob=str(regime_path),
        underlying="NIFTY",
        min_complete_days=2,
        min_iv_rv_aligned_days=1,
        min_regime_days=1,
    )

    assert report.ready is False
    assert report.complete_option_days == 1
    assert report.iv_rv_aligned_days == 1
    assert any(blocker.startswith("complete_option_days=") for blocker in report.blockers)
    assert any(blocker.startswith("regime_days=") for blocker in report.blockers)


def test_option_days_are_counted(tmp_path):
    parquet_path = tmp_path / "option_stream.parquet"
    regime_path = tmp_path / "missing_regimes_*.parquet"
    write_option_parquet(
        parquet_path,
        ["2026-10-01", "2026-10-02"],
    )

    report = evaluate_backtest_readiness(
        warehouse_glob=str(parquet_path),
        regime_glob=str(regime_path),
        underlying="NIFTY",
        min_complete_days=2,
        min_iv_rv_aligned_days=2,
        min_regime_days=0,
    )

    assert report.complete_option_days == 2
    assert report.iv_rv_aligned_days == 2
    assert report.ready is True
    assert report.blockers == []


def test_regime_days_are_counted(tmp_path):
    option_path = tmp_path / "option_stream.parquet"
    regime_path = tmp_path / "market_regime.parquet"

    write_option_parquet(
        option_path,
        ["2026-10-01", "2026-10-02"],
    )

    regime_df = pd.DataFrame(
        [
            {
                "symbol": "NIFTY",
                "ts": pd.Timestamp("2026-10-01 15:30:00", tz="UTC"),
                "regime": "NORMAL_IV_CONTANGO_NORMAL_SKEW",
            },
            {
                "symbol": "NIFTY",
                "ts": pd.Timestamp("2026-10-02 15:30:00", tz="UTC"),
                "regime": "NORMAL_IV_FLAT_TERM_NORMAL_SKEW",
            },
        ]
    )

    conn = duckdb.connect()
    conn.register("regimes", regime_df)
    conn.execute(f"COPY regimes TO '{regime_path.as_posix()}' (FORMAT PARQUET)")
    conn.close()

    report = evaluate_backtest_readiness(
        warehouse_glob=str(option_path),
        regime_glob=str(regime_path),
        underlying="NIFTY",
        min_complete_days=2,
        min_iv_rv_aligned_days=1,
        min_regime_days=2,
    )

    assert report.regime_days == 2
    assert report.ready is True


def test_export_parquet_writes_selected_day(tmp_path: Path):
    store = DuckDBStore(tmp_path / "test.duckdb")

    store.conn.execute(
        """
        INSERT INTO option_stream (
            run_id,
            ts,
            underlying,
            expiry,
            strike,
            option_type,
            tradingsymbol,
            instrument_token,
            lot_size,
            spot,
            ltp,
            bid,
            ask,
            volume,
            oi,
            iv,
            delta,
            gamma,
            vega,
            theta,
            quote_status,
            payload_json
        )
        VALUES (
            'test-run',
            TIMESTAMPTZ '2026-10-20 09:15:00+05:30',
            'NIFTY',
            DATE '2026-10-29',
            25000,
            'CE',
            'NIFTY26O2925000CE',
            12345,
            75,
            25000,
            100,
            99,
            101,
            1000,
            1000,
            0.15,
            0.5,
            0.01,
            10,
            -10,
            'ready',
            '{}'
        )
        """
    )

    output_path = tmp_path / "option_stream.parquet"

    exported_path = store.export_parquet(
        output_path=output_path,
        underlying="NIFTY",
        date_str="2026-10-20",
    )

    assert exported_path.exists()

    store.conn.close()


def test_option_stream_count_for_date(tmp_path: Path):
    store = DuckDBStore(tmp_path / "test.duckdb")

    store.conn.execute(
        """
        INSERT INTO option_stream (
            run_id,
            ts,
            underlying,
            expiry,
            strike,
            option_type,
            tradingsymbol,
            instrument_token,
            lot_size,
            spot,
            ltp,
            bid,
            ask,
            volume,
            oi,
            iv,
            delta,
            gamma,
            vega,
            theta,
            quote_status,
            payload_json
        )
        VALUES (
            'test-run',
            TIMESTAMPTZ '2026-10-20 09:15:00+05:30',
            'NIFTY',
            DATE '2026-10-29',
            25000,
            'CE',
            'NIFTY26O2925000CE',
            12345,
            75,
            25000,
            100,
            99,
            101,
            1000,
            1000,
            0.15,
            0.5,
            0.01,
            10,
            -10,
            'ready',
            '{}'
        )
        """
    )

    count = get_option_stream_count_for_date(
        store=store,
        underlying="NIFTY",
        trading_date=date(2026, 10, 20),
    )

    assert count == 1

    store.conn.close()
