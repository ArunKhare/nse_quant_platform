"""DuckDB persistence for the NSE Quant Decision Platform."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from nse_quant.core.models import ChainSnapshot
from nse_quant.core.settings import get_settings


class DuckDBStore:
    """Owns the DuckDB connection and schema."""

    def __init__(self, path: str | Path | None = None) -> None:
        settings = get_settings()
        self.path = Path(path or settings.storage.db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = duckdb.connect(str(self.path))
        self.conn.execute(  f"SET memory_limit = '{settings.storage.db_memory_limit}'")
        self.conn.execute(f"SET threads = {settings.storage.db_threads}")
        self._create_schema()

    def _create_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS option_stream (
                run_id VARCHAR,
                ts TIMESTAMPTZ,
                underlying VARCHAR,
                expiry DATE,
                strike DOUBLE,
                option_type VARCHAR,
                tradingsymbol VARCHAR,
                instrument_token BIGINT,
                lot_size INTEGER,
                spot DOUBLE,
                ltp DOUBLE,
                bid DOUBLE,
                ask DOUBLE,
                volume BIGINT,
                oi BIGINT,
                iv DOUBLE,
                delta DOUBLE,
                gamma DOUBLE,
                vega DOUBLE,
                theta DOUBLE,
                quote_status VARCHAR,
                payload_json JSON,
                PRIMARY KEY (run_id, ts, instrument_token)
            )
            """
        )

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feature_snapshots (
                feature_id VARCHAR PRIMARY KEY,
                ts TIMESTAMPTZ,
                run_id VARCHAR,
                underlying VARCHAR,
                expiry DATE,
                spot DOUBLE,
                atm_iv DOUBLE,
                iv_rank DOUBLE,
                iv_percentile DOUBLE,
                realized_vol DOUBLE,
                iv_rv_spread DOUBLE,
                pcr DOUBLE,
                total_call_oi BIGINT,
                total_put_oi BIGINT,
                max_pain DOUBLE,
                liquidity_score DOUBLE,
                regime VARCHAR,
                short_momentum DOUBLE,
                straddle_price DOUBLE,
                expected_move_pct DOUBLE,
                expected_move_points DOUBLE,
                diagnostics JSON
            )
            """
        )

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS decisions (
                decision_id VARCHAR PRIMARY KEY,
                ts TIMESTAMPTZ,
                run_id VARCHAR,
                decision_type VARCHAR,
                proposal_id VARCHAR,
                strategy VARCHAR,
                underlying VARCHAR,
                expiry DATE,
                payload JSON
            )
            """
        )

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gate_results (
                gate_result_id VARCHAR PRIMARY KEY,
                ts TIMESTAMPTZ,
                run_id VARCHAR,
                proposal_id VARCHAR,
                strategy VARCHAR,
                gate VARCHAR,
                passed BOOLEAN,
                reason VARCHAR,
                details JSON
            )
            """
        )

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS risk_decisions (
                risk_decision_id VARCHAR PRIMARY KEY,
                ts TIMESTAMPTZ,
                run_id VARCHAR,
                proposal_id VARCHAR,
                strategy VARCHAR,
                approved BOOLEAN,
                reasons JSON,
                checks JSON
            )
            """
        )

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id VARCHAR PRIMARY KEY,
                ts TIMESTAMPTZ,
                run_id VARCHAR,
                proposal_id VARCHAR,
                strategy VARCHAR,
                broker VARCHAR,
                status VARCHAR,
                limit_price DOUBLE,
                filled_price DOUBLE,
                filled_at TIMESTAMPTZ,
                reject_reason VARCHAR,
                payload JSON
            )
            """
        )

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS positions (
                position_id VARCHAR PRIMARY KEY,
                strategy_position_id VARCHAR,
                proposal_id VARCHAR,
                strategy VARCHAR,
                underlying VARCHAR,
                expiry DATE,
                tradingsymbol VARCHAR,
                instrument_token BIGINT,
                option_type VARCHAR,
                strike DOUBLE,
                side VARCHAR,
                lots INTEGER,
                quantity INTEGER,
                opened_at TIMESTAMPTZ,
                entry_price DOUBLE,
                current_price DOUBLE,
                realized_pnl DOUBLE,
                unrealized_pnl DOUBLE,
                status VARCHAR,
                closed_at TIMESTAMPTZ,
                exit_reason VARCHAR
            )
            """
        )

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS strategy_positions (
                strategy_position_id VARCHAR PRIMARY KEY,
                proposal_id VARCHAR,
                strategy VARCHAR,
                underlying VARCHAR,
                expiry DATE,
                opened_at TIMESTAMPTZ,
                entry_price DOUBLE,
                current_price DOUBLE,
                realized_pnl DOUBLE,
                unrealized_pnl DOUBLE,
                status VARCHAR,
                exit_reason VARCHAR,
                all_triggered_exits JSON,
                closed_at TIMESTAMPTZ,
                thesis VARCHAR,
                metadata JSON
            )
            """
        )

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS exit_events (
                exit_event_id VARCHAR PRIMARY KEY,
                ts TIMESTAMPTZ,
                strategy_position_id VARCHAR,
                proposal_id VARCHAR,
                strategy VARCHAR,
                triggered_reasons JSON,
                selected_reason VARCHAR,
                details JSON
            )
            """
        )

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS post_trade_reviews (
                review_id VARCHAR PRIMARY KEY,
                ts TIMESTAMPTZ,
                strategy_position_id VARCHAR,
                proposal_id VARCHAR,
                strategy VARCHAR,
                realized_pnl DOUBLE,
                exit_reason VARCHAR,
                thesis_status VARCHAR,
                decision_quality_notes VARCHAR,
                outcome_notes VARCHAR
            )
            """
        )

        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_feature_snapshots_time
            ON feature_snapshots (underlying, expiry, ts)
            """
        )

        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_option_stream_time
            ON option_stream (underlying, expiry, ts)
            """
        )

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spot_candles (
                instrument_token BIGINT,
                symbol VARCHAR,
                interval VARCHAR,
                ts TIMESTAMPTZ,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT,
                oi BIGINT,
                PRIMARY KEY (instrument_token, interval, ts)
            )
            """
        )

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spot_features (
                symbol VARCHAR,
                ts TIMESTAMPTZ,
                close DOUBLE,
                return_1m DOUBLE,
                rv_1m_30 DOUBLE,
                atr_1m_14 DOUBLE,
                vwap_1m DOUBLE,
                vwap_distance_1m DOUBLE,
                volume_zscore_1m_30 DOUBLE,
                trend_15m DOUBLE,
                atr_15m_14 DOUBLE,
                range_position_15m DOUBLE,
                trend_60m DOUBLE,
                atr_60m_14 DOUBLE,
                range_position_60m DOUBLE,
                PRIMARY KEY (symbol, ts)
            )
            """
        )

        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_spot_features_symbol_ts
            ON spot_features (symbol, ts)
            """
        )

    def write_option_stream(
        self,
        run_id: str,
        snapshot: ChainSnapshot,
        ticks: dict[int, dict[str, Any]] | None = None,
    ) -> int:
        ticks = ticks or {}
        rows = []

        for quote in snapshot.quotes:
            instrument = quote.instrument
            tick = ticks.get(instrument.instrument_token, {})
            rows.append(
                (
                    run_id,
                    snapshot.ts,
                    snapshot.underlying,
                    snapshot.expiry,
                    instrument.strike,
                    instrument.option_type.value,
                    instrument.tradingsymbol,
                    instrument.instrument_token,
                    instrument.lot_size,
                    snapshot.spot,
                    tick.get("ltp", quote.ltp),
                    tick.get("bid", quote.bid),
                    tick.get("ask", quote.ask),
                    tick.get("volume", quote.volume),
                    tick.get("oi", quote.oi),
                    quote.iv,
                    quote.delta,
                    quote.gamma,
                    quote.vega,
                    quote.theta,
                    "ready" if tick else "missing",
                    json.dumps(tick, default=str),
                )
            )

        if rows:
            placeholders = ",".join(["?"] * 22)
            self.conn.executemany(
                f"INSERT OR REPLACE INTO option_stream VALUES ({placeholders})",
                rows,
            )

        return len(rows)

    def latest_iv_history(self, underlying: str, limit: int | None = None) -> list[float]:
        settings = get_settings()
        limit = limit or settings.analytics.iv_history_limit

        rows = self.conn.execute(
            """
            SELECT atm_iv
            FROM (
                SELECT
                    ts,
                    AVG(iv) AS atm_iv
                FROM option_stream
                WHERE underlying = ?
                  AND iv IS NOT NULL
                GROUP BY ts
                ORDER BY ts DESC
                LIMIT ?
            )
            ORDER BY atm_iv
            """,
            [underlying, limit],
        ).fetchall()

        return [float(row[0]) for row in rows if row[0] is not None]

    def export_parquet(self, output_dir: str | Path, date_str: str) -> Path:
        output = Path(output_dir) / f"option_stream_{date_str}.parquet"
        output.parent.mkdir(parents=True, exist_ok=True)

        self.conn.execute(
            """
            COPY (
                SELECT *
                FROM option_stream
                WHERE CAST(ts AS DATE) = ?
            ) TO ? (FORMAT PARQUET)
            """,
            [date_str, str(output)],
        )

        return output

    def close(self) -> None:
        self.conn.close()

    def write_spot_candles(
        self,
        candles: list[dict[str, Any]],
        symbol: str,
        instrument_token: int,
        interval: str,
    ) -> int:
        rows = [
            (
                instrument_token,
                symbol,
                interval,
                candle["date"],
                candle["open"],
                candle["high"],
                candle["low"],
                candle["close"],
                candle["volume"],
                candle.get("oi"),
            )
            for candle in candles
        ]

        self.conn.executemany(
            """
            INSERT OR REPLACE INTO spot_candles VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            rows,
        )

        return len(rows)

    def latest_spot_closes(
        self,
        instrument_token: int,
        interval: str = "minute",
        limit: int = 60,
    ) -> list[float]:
        rows = self.conn.execute(
            """
            SELECT close
            FROM spot_candles
            WHERE instrument_token = ?
            AND interval = ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            [instrument_token, interval, limit],
        ).fetchall()

        return [float(row[0]) for row in reversed(rows)]

    def read_spot_candles(
        self,
        symbol: str,
        interval: str,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
    ) -> pd.DataFrame:
        query = """
            SELECT
                symbol,
                interval,
                ts,
                open,
                high,
                low,
                close,
                volume,
                oi
            FROM spot_candles
            WHERE symbol = ?
              AND interval = ?
        """
        params: list[Any] = [symbol, interval]

        if from_ts is not None:
            query += " AND ts >= ?"
            params.append(from_ts)

        if to_ts is not None:
            query += " AND ts <= ?"
            params.append(to_ts)

        query += " ORDER BY ts"

        return self.conn.execute(query, params).fetchdf()

    def write_spot_features(self, features: pd.DataFrame) -> int:
        if features.empty:
            return 0

        self.conn.register("spot_features_batch", features)

        self.conn.execute(
            """
            INSERT OR REPLACE INTO spot_features
            SELECT
                symbol,
                ts,
                close,
                return_1m,
                rv_1m_30,
                atr_1m_14,
                vwap_1m,
                vwap_distance_1m,
                volume_zscore_1m_30,
                trend_15m,
                atr_15m_14,
                range_position_15m,
                trend_60m,
                atr_60m_14,
                range_position_60m
            FROM spot_features_batch
            """
        )

        self.conn.unregister("spot_features_batch")
        return len(features)

    def write_feature_gate_result(
        self,
        gate_result_id: str,
        ts: datetime,
        run_id: str,
        symbol: str,
        passed: bool,
        reasons: list[str],
        checks: dict[str, bool],
    ) -> None:
        import json
        self.conn.execute(
            """
            INSERT OR REPLACE INTO gate_results VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                gate_result_id,
                ts,
                run_id,
                None,
                "spot_feature_gate",
                "spot_features",
                passed,
                json.dumps(reasons),
                json.dumps(checks),
            ],
        )