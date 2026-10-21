"""DuckDB persistence for the NSE Quant Decision Platform."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from nse_quant.analytics.implied_volatility import (
    implied_volatility,
    time_to_expiry_years,
)
from nse_quant.core.constants import IST
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

    def __init__(self, path: str | Path | None = None,*, read_only:bool = False) -> None:
        settings = get_settings()
        self.path = Path(path or settings.storage.db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = duckdb.connect(str(self.path), read_only=read_only,)
        self.conn.execute(  f"SET memory_limit = '{settings.storage.db_memory_limit}'")
        self.conn.execute(f"SET threads = {settings.storage.db_threads}")
        if not read_only:
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
            CREATE TABLE IF NOT EXISTS underlying_iv_observations (
                ts TIMESTAMPTZ NOT NULL,
                underlying VARCHAR NOT NULL,
                expiry DATE NOT NULL,
                iv DOUBLE NOT NULL,
                spot DOUBLE,
                source VARCHAR NOT NULL,
                PRIMARY KEY (ts, underlying, expiry)
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

        IV_OBSERVATIONS_SQL = """
            CREATE TABLE IF NOT EXISTS underlying_iv_observations (
                ts TIMESTAMPTZ NOT NULL,
                underlying VARCHAR NOT NULL,
                expiry DATE NOT NULL,
                iv DOUBLE NOT NULL,
                spot DOUBLE,
                source VARCHAR NOT NULL,
                PRIMARY KEY (ts, underlying, expiry)
            )
            """
        self.conn.execute(IV_OBSERVATIONS_SQL)

        DAILY_IV= """
            CREATE TABLE IF NOT EXISTS daily_rv_observations (
                symbol VARCHAR NOT NULL,
                trading_date DATE NOT NULL,
                rv DOUBLE NOT NULL,
                observation_count BIGINT NOT NULL,
                PRIMARY KEY (symbol, trading_date)
            )
            """
        self.conn.execute(DAILY_IV)

    def _compute_option_iv(
        self,
        *,
        ts: datetime,
        spot: float | None,
        expiry: date,
        strike: float,
        option_type: str,
        ltp: float | None,
    ) -> float | None:
        settings = get_settings()

        if spot is None or ltp is None or ltp <= 0:
            return None

        expiry_dt = datetime.combine(
            expiry,
            time(15, 30),
            tzinfo=IST,
        )

        iv = implied_volatility(
            option_price=ltp,
            spot=spot,
            strike=strike,
            time_to_expiry_years=time_to_expiry_years(
                as_of=ts,
                expiry=expiry_dt,
            ),
            risk_free_rate=settings.market_data.risk_free_rate,
            option_type=option_type,
        )

        if iv is None or not 0.001 <= iv <= 5.0:
            return None
        return iv

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

            ltp = tick.get("ltp", quote.ltp)

            iv = quote.iv

            if iv is None:
                iv = self._compute_option_iv(
                    ts=snapshot.ts,
                    spot=snapshot.spot,
                    expiry=snapshot.expiry,
                    strike=instrument.strike,
                    option_type=instrument.option_type.value,
                    ltp=ltp,
                )

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
                    ltp,
                    tick.get("bid", quote.bid),
                    tick.get("ask", quote.ask),
                    tick.get("volume", quote.volume),
                    tick.get("oi", quote.oi),
                    iv,
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
        if rows:
            self._write_atm_iv_observation(
                run_id=run_id,
                snapshot=snapshot,
                rows=rows,
            )
        return len(rows)

    def _write_atm_iv_observation(
        self,
        *,
        run_id: str,
        snapshot: ChainSnapshot,
        rows: list[tuple[Any, ...]],
    ) -> None:
        valid_ivs = [
            (row[4], row[15])
            for row in rows
            if row[15] is not None
        ]

        if not valid_ivs or snapshot.spot is None:
            return

        atm_strike = min(
            valid_ivs,
            key=lambda item: abs(item[0] - snapshot.spot),
        )[0]

        atm_ivs = [
            iv
            for strike, iv in valid_ivs
            if strike == atm_strike
        ]

        if not atm_ivs:
            return

        atm_iv = sum(atm_ivs) / len(atm_ivs)

        self.conn.execute(
            """
            INSERT OR REPLACE INTO underlying_iv_observations VALUES (
                ?, ?, ?, ?, ?, ?
            )
            """,
            [
                snapshot.ts,
                snapshot.underlying,
                snapshot.expiry,
                atm_iv,
                snapshot.spot,
                "atm_average_live",
            ],
        )

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

    def export_parquet(
        self,
        *,
        output_path: Path,
        underlying: str,
        date_str: str,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self.conn.execute(
            f"""
            COPY (
                SELECT *
                FROM option_stream
                WHERE underlying = ?
                AND CAST(ts AS DATE) = ?
            ) TO '{output_path.as_posix()}' (FORMAT PARQUET)
            """,
            [underlying, date_str],
        )

        return output_path

    def close(self) -> None:
        self.conn.close()

    def export_market_regime_parquet(
        self,
        *,
        output_path: Path,
        underlying: str,
        date_str: str,
    ) -> Path:
        """Export one day's latest market regime to Parquet."""

        output_path.parent.mkdir(parents=True, exist_ok=True)

        self.conn.execute(
            f"""
            COPY (
                SELECT
                    symbol,
                    ts,
                    trend_regime,
                    volatility_regime,
                    iv_regime,
                    regime,
                    features
                FROM market_regimes
                WHERE symbol = ?
                AND CAST(ts AS DATE) = ?
                QUALIFY row_number() OVER (
                    PARTITION BY symbol
                    ORDER BY ts DESC
                ) = 1
            ) TO '{output_path.as_posix()}' (FORMAT PARQUET)
            """,
            [underlying, date_str],
        )

        return output_path
    def write_spot_candles(
        self,
        candles: list[dict[str, Any]],
        symbol: str,
        instrument_token: int,
        interval: str,
    ) -> int:
        for candle in candles:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO spot_candles (
                    instrument_token,
                    symbol,
                    interval,
                    ts,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    oi
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
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
                ],
            )

        return len(candles)

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

    def write_underlying_iv_observation(
        self,
        *,
        ts: datetime,
        underlying: str,
        expiry: date,
        iv: float,
        spot: float | None,
        source: str = "atm_average",
    ) -> int:
        """Insert or replace one underlying-level IV observation."""
        self.conn.execute(
            """
            INSERT OR REPLACE INTO underlying_iv_observations
                (ts, underlying, expiry, iv, spot, source)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [ts, underlying, expiry, iv, spot, source],
        )
        return 1

    def get_underlying_iv_observations(
        self,
        *,
        underlying: str,
        expiry: date | None = None,
        limit: int | None = None,
    ) -> list[tuple[datetime, float, float | None]]:
        query = """
            SELECT ts, iv, spot
            FROM underlying_iv_observations
            WHERE underlying = ?
        """
        params: list[Any] = [underlying]

        if expiry is not None:
            query += " AND expiry = ?"
            params.append(expiry)

        query += " ORDER BY ts"

        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        return self.conn.execute(query, params).fetchall()

    def count_underlying_iv_observations(
        self,
        *,
        underlying: str,
        expiry: date | None = None,
    ) -> int:
        query = """
            SELECT COUNT(*)
            FROM underlying_iv_observations
            WHERE underlying = ?
        """
        params: list[Any] = [underlying]

        if expiry is not None:
            query += " AND expiry = ?"
            params.append(expiry)

        row = self.conn.execute(query, params).fetchone()
        return row[0] if row is not None else 0

    def count_aligned_iv_rv_observations(
        self,
        *,
        symbol: str,
        as_of: datetime,
    ) -> int:
        """Count trading dates with both IV and realized-volatility data."""
        row = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT
                    CAST(iv.ts AS DATE) AS trading_date
                FROM underlying_iv_observations AS iv
                INNER JOIN daily_rv_observations AS rv
                    ON rv.symbol = ?
                   AND rv.trading_date = CAST(iv.ts AS DATE)
                WHERE iv.underlying = ?
                  AND iv.ts < ?
                GROUP BY CAST(iv.ts AS DATE)
            )
            """,
            [symbol, symbol, as_of],
        ).fetchone()
        return int(row[0]) if row is not None else 0

    def write_daily_rv_observation(
        self,
        *,
        symbol: str,
        trading_date: date,
        rv: float,
        observation_count: int,
    ) -> int:

        self.conn.execute(
            """
            INSERT OR REPLACE INTO daily_rv_observations VALUES (
                ?, ?, ?, ?
            )
            """,
            [symbol, trading_date, rv, observation_count],
        )
        return 1

    def get_daily_rv_dates(
        self,
        *,
        symbol: str,
        as_of: datetime,
    ) -> list[date]:
        rows = self.conn.execute(
            """
            SELECT trading_date
            FROM daily_rv_observations
            WHERE symbol = ?
              AND trading_date < ?
            ORDER BY trading_date
            """,
            [symbol, as_of.date()],
        ).fetchall()

        return [row[0] for row in rows]

    def is_trading_day(self, day: date | None = None) -> bool:
        """Return True when the given IST date is an NSE trading day."""
        day = day or datetime.now(IST).date()

        return day.weekday() >= 5

    def write_daily_iv_regime(
        self,
        *,
        trade_date: date,
        underlying: str,
        iv_level: str,
        iv_term_regime: str,
        iv_skew_regime: str,
        iv_regime: str,
        metrics: dict[str, Any],
    ) -> int:
        """Persist one daily IV regime observation."""
        self.conn.execute(
            """
            INSERT OR REPLACE INTO market_regimes VALUES (
                ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                underlying,
                trade_date,
                "neutral",
                iv_level,
                iv_regime,
                iv_regime,
                json.dumps(
                    {
                        "iv_level": iv_level,
                        "iv_term_regime": iv_term_regime,
                        "iv_skew_regime": iv_skew_regime,
                        **metrics,
                    },
                    default=str,
                ),
            ],
        )

        return 1

    def latest_daily_iv_regime(
        self,
        *,
        underlying: str,
        as_of: date | None = None,
    ) -> dict[str, Any] | None:
        """Return the most recent persisted daily IV regime."""
        as_of = as_of or date.today()

        row = self.conn.execute(
            """
            SELECT
                ts,
                trend_regime,
                volatility_regime,
                iv_regime,
                features
            FROM market_regimes
            WHERE symbol = ?
              AND CAST(ts AS DATE) <= ?
            ORDER BY ts DESC
            LIMIT 1
            """,
            [underlying, as_of],
        ).fetchone()

        if row is None:
            return None

        return {
            "trade_date": row[0],
            "trend_regime": row[1],
            "volatility_regime": row[2],
            "iv_regime": row[3],
            "features": (
                json.loads(row[4])
                if row[4]
                else {}
            ),
        }

    def refresh_latest_spot_feature(
        self,
        *,
        symbol: str,
        instrument_token: int,
        as_of: datetime,
    ) -> None:
        """Refresh the latest spot feature snapshot from recent 1m candles."""

        rows = self.conn.execute(
            """
            SELECT
                ts,
                open,
                high,
                low,
                close,
                volume
            FROM spot_candles
            WHERE symbol = ?
              AND instrument_token = ?
              AND interval = '1m'
            ORDER BY ts DESC
            LIMIT 60
            """,
            [symbol, instrument_token],
        ).fetchall()

        if not rows:
            return

        rows = list(reversed(rows))

        latest_ts = rows[-1][0]
        latest_close = rows[-1][4]
        latest_volume = rows[-1][5]

        closes = [float(row[4]) for row in rows]
        highs = [float(row[2]) for row in rows]
        lows = [float(row[3]) for row in rows]
        volumes = [float(row[5] or 0) for row in rows]

        return_1m = None
        rv_1m_30 = None
        atr_1m_14 = None
        vwap_1m = None
        vwap_distance_1m = None
        volume_zscore_1m_30 = None
        trend_15m = None
        atr_15m_14 = None
        range_position_15m = None
        trend_60m = None
        atr_60m_14 = None
        range_position_60m = None

        if len(closes) >= 2 and closes[-2]:
            return_1m = (
                closes[-1] / closes[-2]
            ) - 1

        if len(closes) >= 3:
            returns = [
                (closes[index] / closes[index - 1]) - 1
                for index in range(1, len(closes))
                if closes[index - 1]
            ]

            if len(returns) >= 2:
                mean_return = sum(returns) / len(returns)

                variance = sum(
                    (value - mean_return) ** 2
                    for value in returns
                ) / (len(returns) - 1)

                rv_1m_30 = (variance ** 0.5) * (
                    (252 * 375) ** 0.5
                )

        if len(rows) >= 2:
            true_ranges = []

            for index in range(1, len(rows)):
                high = highs[index]
                low = lows[index]
                previous_close = closes[index - 1]

                true_ranges.append(
                    max(
                        high - low,
                        abs(high - previous_close),
                        abs(low - previous_close),
                    )
                )

            recent_true_ranges = true_ranges[-14:]

            if recent_true_ranges:
                atr_1m_14 = (
                    sum(recent_true_ranges)
                    / len(recent_true_ranges)
                )

        if latest_volume > 0:
            weighted_prices = []

            for index in range(len(rows)):
                typical_price = (
                    highs[index]
                    + lows[index]
                    + closes[index]
                ) / 3

                weighted_prices.append(
                    typical_price * volumes[index]
                )

            total_volume = sum(volumes)

            if total_volume > 0:
                vwap_1m = (
                    sum(weighted_prices) / total_volume
                )

                vwap_distance_1m = (
                    latest_close - vwap_1m
                ) / vwap_1m

        if len(volumes) >= 2:
            recent_volumes = volumes[-30:]

            mean_volume = (
                sum(recent_volumes) / len(recent_volumes)
            )

            if mean_volume > 0:
                variance = sum(
                    (value - mean_volume) ** 2
                    for value in recent_volumes
                ) / len(recent_volumes)

                std_volume = variance ** 0.5

                if std_volume > 0:
                    volume_zscore_1m_30 = (
                        (latest_volume - mean_volume)
                        / std_volume
                    )

        if len(closes) >= 16:
            trend_15m = closes[-1] - closes[-16]

            recent_rows = rows[-15:]

            recent_highs = [float(row[2]) for row in recent_rows]
            recent_lows = [float(row[3]) for row in recent_rows]

            high_low_range = max(recent_highs) - min(recent_lows)

            if high_low_range > 0:
                range_position_15m = (
                    latest_close - min(recent_lows)
                ) / high_low_range

            true_ranges = []

            for index in range(1, len(recent_rows)):
                high = recent_highs[index]
                low = recent_lows[index]
                previous_close = closes[-len(recent_rows) + index - 1]

                true_ranges.append(
                    max(
                        high - low,
                        abs(high - previous_close),
                        abs(low - previous_close),
                    )
                )

            if true_ranges:
                atr_15m_14 = (
                    sum(true_ranges) / len(true_ranges)
                )

        if len(closes) >= 61:
            trend_60m = closes[-1] - closes[-61]

            recent_rows = rows[-60:]

            recent_highs = [float(row[2]) for row in recent_rows]
            recent_lows = [float(row[3]) for row in recent_rows]

            high_low_range = max(recent_highs) - min(recent_lows)

            if high_low_range > 0:
                range_position_60m = (
                    latest_close - min(recent_lows)
                ) / high_low_range

            true_ranges = []

            for index in range(1, len(recent_rows)):
                high = recent_highs[index]
                low = recent_lows[index]
                previous_close = closes[-len(recent_rows) + index - 1]

                true_ranges.append(
                    max(
                        high - low,
                        abs(high - previous_close),
                        abs(low - previous_close),
                    )
                )

            if true_ranges:
                atr_60m_14 = (
                    sum(true_ranges) / len(true_ranges)
                )

        self.conn.execute(
            """
            INSERT OR REPLACE INTO spot_features (
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
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                symbol,
                latest_ts,
                latest_close,
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
                range_position_60m,
            ],
        )