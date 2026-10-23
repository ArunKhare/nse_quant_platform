"""Decision-quality analytics over persisted platform events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from nse_quant.persistence.duckdb_store import DuckDBStore


@dataclass(frozen=True)
class DecisionAnalyticsRepository:
    store: DuckDBStore

    def feature_gate_summary(
        self,
        run_id: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
    ) -> pd.DataFrame:
        query = """
            SELECT
                CAST(ts AS DATE) AS date,
                passed,
                COUNT(*) AS cycles,
                COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (
                    PARTITION BY CAST(ts AS DATE)
                ) AS pct
            FROM gate_results
            WHERE gate = 'spot_features'
        """
        params: list[object] = []

        if run_id is not None:
            query += " AND run_id = ?"
            params.append(run_id)

        if from_ts is not None:
            query += " AND ts >= ?"
            params.append(from_ts)

        if to_ts is not None:
            query += " AND ts <= ?"
            params.append(to_ts)

        query += """
            GROUP BY date, passed
            ORDER BY date, passed
        """

        return self.store.conn.execute(query, params).fetchdf()

    def rejection_reasons(
        self,
        run_id: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
    ) -> pd.DataFrame:
        query = """
            SELECT
                CAST(ts AS DATE) AS date,
                json_extract_string(reason, '$[0]') AS reason,
                COUNT(*) AS occurrences
            FROM gate_results
            WHERE gate = 'spot_features'
              AND passed = false
        """
        params: list[object] = []

        if run_id is not None:
            query += " AND run_id = ?"
            params.append(run_id)

        if from_ts is not None:
            query += " AND ts >= ?"
            params.append(from_ts)

        if to_ts is not None:
            query += " AND ts <= ?"
            params.append(to_ts)

        query += """
            GROUP BY date, reason
            ORDER BY date, occurrences DESC
        """

        return self.store.conn.execute(query, params).fetchdf()

    def funnel(
        self,
        run_id: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
    ) -> pd.DataFrame:
        query = """
                WITH gates AS (
                    SELECT
                        CAST(ts AS DATE) AS date,
                        COUNT(*) AS feature_cycles,
                        SUM(CASE WHEN passed THEN 1 ELSE 0 END)
                            AS feature_passed
                    FROM gate_results
                    WHERE gate = 'spot_features'
                ),
                signals AS (
                    SELECT
                        CAST(ts AS DATE) AS date,
                        COUNT(*) AS proposals
                    FROM decisions
                    WHERE decision_type = 'signal'
                ),
                risk AS (
                    SELECT
                        CAST(ts AS DATE) AS date,
                        SUM(CASE WHEN approved THEN 1 ELSE 0 END)
                            AS risk_approved
                    FROM risk_decisions
                )
                SELECT
                    COALESCE(g.date, s.date, r.date) AS date,
                    COALESCE(g.feature_cycles, 0) AS feature_cycles,
                    COALESCE(g.feature_passed, 0) AS feature_passed,
                    COALESCE(s.proposals, 0) AS proposals,
                    COALESCE(r.risk_approved, 0) AS risk_approved
                FROM gates g
                FULL JOIN signals s
                    ON g.date = s.date
                FULL JOIN risk r
                    ON COALESCE(g.date, s.date) = r.date
                WHERE 1 = 1
            """

        params: list[object] = []

        if from_ts is not None:
            query += " AND COALESCE(g.date, s.date, r.date) >= ?"
            params.append(from_ts)

        if to_ts is not None:
            query += " AND COALESCE(g.date, s.date, r.date) <= ?"
            params.append(to_ts)

        query += """
                GROUP BY
                    COALESCE(g.date, s.date, r.date)
                ORDER BY
                    COALESCE(g.date, s.date, r.date)
            """

        return self.store.conn.execute(query, params).fetchdf()
