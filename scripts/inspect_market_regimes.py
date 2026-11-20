"""Read-only inspection of persisted market regimes."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from nse_quant.core.settings import get_settings


def main() -> None:
    settings = get_settings()
    db_path = Path(settings.storage.db_path)

    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    symbol = settings.market_data.default_symbol
    conn = duckdb.connect(str(db_path), read_only=True)

    try:
        print(f"Database: {db_path}")
        print(f"Symbol: {symbol}\n")

        print("=== Latest 20 market-regime rows ===")
        latest = conn.execute(
            """
            SELECT
                ts,
                trend_regime,
                volatility_regime,
                iv_regime,
                regime,
                features
            FROM market_regimes
            WHERE symbol = ?
            ORDER BY ts DESC
            LIMIT 20
            """,
            [symbol],
        ).fetchall()

        if not latest:
            print("No market_regimes rows found.")
            return

        for row in latest:
            ts, trend, vol, iv, regime, features_json = row
            print(f"{ts} | trend={trend} vol={vol} iv={iv} regime={regime}")

            try:
                features = json.loads(features_json) if features_json else {}
            except (TypeError, json.JSONDecodeError):
                features = {}

            print(
                "    close={close} sma50={sma50} atr14={atr14} "
                "norm_dist={normalized_trend_distance} "
                "rv={realized_volatility} rv_pct={rv_percentile} "
                "iv_rank={iv_rank} iv_pct={iv_percentile}".format(
                    close=features.get("close"),
                    sma50=features.get("sma50"),
                    atr14=features.get("atr14"),
                    normalized_trend_distance=features.get("normalized_trend_distance"),
                    realized_volatility=features.get("realized_volatility"),
                    rv_percentile=features.get("rv_percentile"),
                    iv_rank=features.get("iv_rank"),
                    iv_percentile=features.get("iv_percentile"),
                )
            )

        print("\n=== Regime counts, last 7 calendar days ===")
        counts = conn.execute(
            """
            SELECT
                regime,
                COUNT(*) AS row_count,
                MIN(ts) AS first_ts,
                MAX(ts) AS last_ts
            FROM market_regimes
            WHERE symbol = ?
              AND ts >= CURRENT_TIMESTAMP - INTERVAL 7 DAY
            GROUP BY regime
            ORDER BY row_count DESC
            """,
            [symbol],
        ).fetchall()

        if counts:
            for regime, count, first_ts, last_ts in counts:
                print(f"{regime}: {count} rows | {first_ts} -> {last_ts}")
        else:
            print("No regime rows in the last 7 days.")

        print("\n=== Latest row freshness ===")
        freshness = conn.execute(
            """
            SELECT
                ts,
                regime,
                DATE_DIFF(
                    'second',
                    ts,
                    CURRENT_TIMESTAMP
                ) AS age_seconds
            FROM market_regimes
            WHERE symbol = ?
            ORDER BY ts DESC
            LIMIT 1
            """,
            [symbol],
        ).fetchone()

        if freshness:
            ts, regime, age_seconds = freshness
            print(f"Latest: {ts} | regime={regime} | age={age_seconds} seconds")

            if age_seconds > settings.runtime.stale_seconds:
                print(f"WARNING: latest regime is older than runtime.stale_seconds={settings.runtime.stale_seconds}.")

        print("\n=== Potential IV-regime inconsistencies ===")
        inconsistent = conn.execute(
            """
            SELECT
                ts,
                regime,
                iv_regime,
                json_extract_string(features, '$.iv_rank') AS iv_rank,
                json_extract_string(features, '$.iv_percentile')
                    AS iv_percentile
            FROM market_regimes
            WHERE symbol = ?
              AND ts >= CURRENT_TIMESTAMP - INTERVAL 7 DAY
              AND (
                    (iv_regime = 'HIGH'
                     AND COALESCE(
                         TRY_CAST(
                             json_extract_string(features, '$.iv_rank')
                             AS DOUBLE
                         ),
                         TRY_CAST(
                             json_extract_string(features, '$.iv_percentile')
                             AS DOUBLE
                         )
                     ) < 70)
                 OR (iv_regime = 'LOW'
                     AND COALESCE(
                         TRY_CAST(
                             json_extract_string(features, '$.iv_rank')
                             AS DOUBLE
                         ),
                         TRY_CAST(
                             json_extract_string(features, '$.iv_percentile')
                             AS DOUBLE
                         )
                     ) > 30)
                 OR (iv_regime = 'NORMAL'
                     AND (
                         COALESCE(
                             TRY_CAST(
                                 json_extract_string(features, '$.iv_rank')
                                 AS DOUBLE
                             ),
                             TRY_CAST(
                                 json_extract_string(
                                     features, '$.iv_percentile'
                                 ) AS DOUBLE
                             )
                         ) >= 70
                         OR COALESCE(
                             TRY_CAST(
                                 json_extract_string(features, '$.iv_rank')
                                 AS DOUBLE
                             ),
                             TRY_CAST(
                                 json_extract_string(
                                     features, '$.iv_percentile'
                                 ) AS DOUBLE
                             )
                         ) <= 30
                     ))
              )
            ORDER BY ts DESC
            LIMIT 20
            """,
            [symbol],
        ).fetchall()

        if inconsistent:
            for row in inconsistent:
                print(row)
        else:
            print("No obvious IV-regime inconsistencies found.")

        print("\n=== ATR ===")
        atr_rows = conn.execute(
            """
            SELECT
                ts,
                TRY_CAST(
                    json_extract_string(features, '$.close') AS DOUBLE
                ) AS close,
                TRY_CAST(
                    json_extract_string(features, '$.sma50') AS DOUBLE
                ) AS sma50,
                TRY_CAST(
                    json_extract_string(features, '$.atr14') AS DOUBLE
                ) AS atr14,
                TRY_CAST(
                    json_extract_string(
                        features,
                        '$.normalized_trend_distance'
                    ) AS DOUBLE
                ) AS normalized_distance,
                regime
            FROM market_regimes
            WHERE symbol = 'NIFTY'
            ORDER BY ts DESC
            LIMIT 30
            """
        ).fetchall()

        print(f"{'ts':<26} {'close':>12} {'sma50':>12} {'atr14':>10} {'norm_dist':>14} regime")

        for ts, close, sma50, atr14, norm_dist, regime in atr_rows:
            print(f"{str(ts):<26} {close:>12.2f} {sma50:>12.2f} {atr14:>10.4f} {norm_dist:>14.2f} {regime}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
