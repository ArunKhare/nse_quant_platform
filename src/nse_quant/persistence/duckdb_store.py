"""DuckDB persistence for the NSE Quant Decision Platform."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from nse_quant.core.models import ChainSnapshot
from nse_quant.core.settings import get_settings


def _as_json_object(value: Any) -> Any:
    """Normalize DuckDB JSON values that may be strings or parsed objects."""
    if value is None or value == "":
        return {}

    if isinstance(value, (dict, list, set)):
        return value

    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}

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

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_regimes (
                symbol VARCHAR,
                ts TIMESTAMPTZ,
                trend_regime VARCHAR,
                volatility_regime VARCHAR,
                iv_regime VARCHAR,
                regime VARCHAR,
                features JSON,
                PRIMARY KEY (symbol, ts)
            )
            """
        )

        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_market_regimes_symbol_ts
            ON market_regimes (symbol, ts)
            """
        )

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS regime_policies (
                policy_id VARCHAR PRIMARY KEY,
                symbol VARCHAR,
                train_start DATE,
                train_end DATE,
                test_start DATE,
                test_end DATE,
                allowed_regimes JSON,
                regime_metrics JSON,
                selection_status VARCHAR,
                risk_limits JSON,
                created_at TIMESTAMPTZ
            )
            """
        )

        regime_policy_columns = {
            row[1]
            for row in self.conn.execute(
                """
                PRAGMA table_info('regime_policies')
                """
            ).fetchall()
        }

        if "risk_limits" not in regime_policy_columns:
            self.conn.execute(
                """
                ALTER TABLE regime_policies
                ADD COLUMN risk_limits JSON
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
    def write_feature_availability_result(
        self,
        gate_result_id: str,
        ts: datetime,
        run_id: str,
        symbol: str,
        passed: bool,
        reasons: list[str],
        checks: dict[str, Any],
    ) -> None:
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
                "feature_availability",
                "feature_availability",
                passed,
                json.dumps(reasons),
                json.dumps(checks, default=str),
            ],
        )

    def write_market_regime(
        self,
        *,
        symbol: str,
        ts: datetime,
        trend_regime: str,
        volatility_regime: str,
        iv_regime: str,
        regime: str,
        features: dict[str, Any],
    ) -> None:

        self.conn.execute(
            """
            INSERT OR REPLACE INTO market_regimes VALUES (
                ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                symbol,
                ts,
                trend_regime,
                volatility_regime,
                iv_regime,
                regime,
                json.dumps(features, default=str),
            ],
        )

    def get_market_regime_as_of(
        self,
        symbol: str,
        ts: datetime,
    ) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT
                trend_regime,
                volatility_regime,
                iv_regime,
                regime,
                features
            FROM market_regimes
            WHERE symbol = ?
              AND ts <= ?
            ORDER BY ts DESC
            LIMIT 1
            """,
            [symbol, ts],
        ).fetchone()

        if row is None:
            return None

        return {
            "trend_regime": row[0],
            "volatility_regime": row[1],
            "iv_regime": row[2],
            "regime": row[3],
            "features": json.loads(row[4]) if row[4] else {},
        }
    def save_regime_policy(
        self,
        *,
        policy_id: str,
        symbol: str,
        train_start: Any,
        train_end: Any,
        test_start: Any,
        test_end: Any,
        policy: Any,
        risk_limits: dict[str, Any] | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO regime_policies VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                policy_id,
                symbol,
                train_start,
                train_end,
                test_start,
                test_end,
                json.dumps(sorted(policy.allowed_regimes)),
                json.dumps(policy.regime_metrics, default=str),
                policy.selection_status,
                datetime.now(UTC),
                json.dumps(risk_limits or {}, default=str),
            ],
        )

    def latest_regime_policy(
        self,
        symbol: str,
        as_of: datetime,
    ) -> dict[str, Any] | None:
        as_of_date = as_of.date() if isinstance(as_of, datetime) else as_of

        row = self.conn.execute(
            """
            SELECT
                policy_id,
                allowed_regimes,
                selection_status,
                test_end,
                risk_limits
            FROM regime_policies
            WHERE symbol = ?
              AND test_start <= ?
              AND test_end >= ?
            ORDER BY test_start DESC
            LIMIT 1
            """,
            [symbol, as_of_date, as_of_date],
        ).fetchone()

        if row is not None:
            status = row[1]
        else:
            row = self.conn.execute(
                """
                SELECT
                    policy_id,
                    allowed_regimes,
                    selection_status,
                    test_end,
                    risk_limits
                FROM regime_policies
                WHERE symbol = ?
                  AND test_end < ?
                ORDER BY test_end DESC
                LIMIT 1
                """,
                [symbol, as_of_date],
            ).fetchone()

            if row is None:
                return None
            status = 'STALE'

        allowed_regimes = _as_json_object(row[1])
        risk_limits = _as_json_object(row[4])

        if isinstance(allowed_regimes, str):
            allowed_regimes = _as_json_object(allowed_regimes)

        return {
            "policy_id": row[0],
            "allowed_regimes": set(
                allowed_regimes
                if isinstance(allowed_regimes, list)
                else []
            ),
            "selection_status": status,
            "test_end": row[3],
            "risk_limits": (
                risk_limits
                if isinstance(risk_limits, dict)
                else {}
            ),
        }