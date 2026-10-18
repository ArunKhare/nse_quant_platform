"""DuckDB persistence for the NSE Quant Decision Platform."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from nse_quant.core.models import ChainSnapshot
from nse_quant.core.settings import get_settings


class DuckDBStore:
    """Owns the DuckDB connection and schema."""

    def __init__(self, path: str | Path | None = None) -> None:
        settings = get_settings()
        self.path = Path(path or settings.storage.db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = duckdb.connect(str(self.path))
        self.conn.execute("SET memory_limit = '512MB'")
        self.conn.execute("SET threads = 2")
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