"""Evaluate whether sufficient point-in-time history exists."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from nse_quant.features.availability import (
    CORE_1M_REQUIREMENTS,
    HTF_REQUIREMENTS,
    IV_REQUIREMENTS,
    FeatureAvailability,
    FeatureAvailabilityReport,
)


class FeatureAvailabilityChecker:
    def __init__(self, store: Any) -> None:
        self._store = store

    def evaluate(
        self,
        symbol: str,
        instrument_token: int,
        as_of: datetime,
    ) -> FeatureAvailabilityReport:
        observations: dict[str, int] = {}
        missing: list[str] = []
        reasons: list[str] = []

        core_counts = self._candle_counts(
            instrument_token=instrument_token,
            intervals=["1m"],
            as_of=as_of,
        )
        htf_counts = self._candle_counts(
            instrument_token=instrument_token,
            intervals=["15m", "60m"],
            as_of=as_of,
        )

        observations.update(core_counts)
        observations.update(htf_counts)

        core_status = self._evaluate_requirements(
            CORE_1M_REQUIREMENTS,
            observations,
            missing,
            reasons,
        )

        htf_status = self._evaluate_requirements(
            HTF_REQUIREMENTS,
            observations,
            missing,
            reasons,
        )

        iv_counts = self._iv_counts(
            symbol=symbol,
            as_of=as_of,
        )
        observations.update(iv_counts)

        iv_status = self._evaluate_requirements(
            IV_REQUIREMENTS,
            observations,
            missing,
            reasons,
        )

        if core_status == FeatureAvailability.UNAVAILABLE:
            overall_status = FeatureAvailability.UNAVAILABLE
        elif (
            htf_status == FeatureAvailability.WARMING_UP
            or iv_status == FeatureAvailability.WARMING_UP
        ) or (
            htf_status == FeatureAvailability.UNAVAILABLE
            or iv_status == FeatureAvailability.UNAVAILABLE
        ):
            overall_status = FeatureAvailability.WARMING_UP
        else:
            overall_status = FeatureAvailability.READY

        return FeatureAvailabilityReport(
            symbol=symbol,
            as_of=as_of,
            core_status=core_status,
            htf_status=htf_status,
            iv_status=iv_status,
            overall_status=overall_status,
            observations=observations,
            missing=missing,
            reasons=reasons,
        )

    def _candle_counts(
        self,
        *,
        instrument_token: int,
        intervals: list[str],
        as_of: datetime,
    ) -> dict[str, int]:
        counts: dict[str, int] = {}

        for interval in intervals:
            counts[interval] = int(
                self._store.conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM spot_candles
                    WHERE instrument_token = ?
                      AND interval = ?
                      AND ts < ?
                    """,
                    [instrument_token, interval, as_of],
                ).fetchone()[0]
            )

        return counts

    def _iv_counts(
        self,
        *,
        symbol: str,
        as_of: datetime,
    ) -> dict[str, int]:
        iv_observations = int(
            self._store.conn.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT ts
                    FROM option_stream
                    WHERE underlying = ?
                      AND ts < ?
                      AND iv IS NOT NULL
                    GROUP BY ts
                )
                """,
                [symbol, as_of],
            ).fetchone()[0]
        )

        aligned_count = getattr(
            self._store,
            "count_aligned_iv_rv_observations",
            None,
        )

        if callable(aligned_count):
            iv_rv_aligned_observations = int(
                cast(
                    Any,
                    aligned_count(
                        symbol=symbol,
                        as_of=as_of,
                    ),
                )
            )
        else:
            iv_rv_aligned_observations = min(
                iv_observations,
                self._daily_spot_observation_count(
                    symbol=symbol,
                    as_of=as_of,
                ),
            )

        iv_days_row = self._store.conn.execute(
            """
            SELECT COUNT(DISTINCT CAST(ts AS DATE))
            FROM option_stream
            WHERE underlying = ?
              AND ts < ?
              AND iv IS NOT NULL
            """,
            [symbol, as_of],
        ).fetchone()

        return {
            "iv_observations": iv_observations,
            "iv_days": int(iv_days_row[0]),
            "iv_rv_aligned_observations": int(iv_rv_aligned_observations),
        }

    def _daily_spot_observation_count(
        self,
        *,
        symbol: str,
        as_of: datetime,
    ) -> int:
        return int(
            self._store.conn.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT CAST(ts AS DATE) AS trading_date
                    FROM spot_candles
                    WHERE symbol = ?
                      AND interval = 'day'
                      AND ts < ?
                    GROUP BY trading_date
                )
                """,
                [symbol, as_of],
            ).fetchone()[0]
        )

    @staticmethod
    def _evaluate_requirements(
        requirements,
        observations: dict[str, int],
        missing: list[str],
        reasons: list[str],
    ) -> FeatureAvailability:
        statuses: list[FeatureAvailability] = []

        for requirement in requirements:
            available = requirement.required_observations
            observation_key = (
                requirement.interval
                if requirement.source == "spot_candles"
                else requirement.feature
            )

            if requirement.feature == "iv_rank":
                count = observations.get("iv_observations", 0)
            elif requirement.feature == "iv_rv_spread":
                count = observations.get(
                    "iv_rv_aligned_observations",
                    0,
                )
            else:
                count = observations.get(observation_key, 0)

            if count >= available:
                statuses.append(FeatureAvailability.READY)
                continue

            if count > 0:
                statuses.append(FeatureAvailability.WARMING_UP)
                reasons.append(f"{requirement.feature}: {count}/{available} observations")
            else:
                statuses.append(FeatureAvailability.UNAVAILABLE)
                missing.append(requirement.feature)
                reasons.append(f"{requirement.feature}: no observations; requires {available}")

        if FeatureAvailability.UNAVAILABLE in statuses:
            return FeatureAvailability.UNAVAILABLE

        if FeatureAvailability.WARMING_UP in statuses:
            return FeatureAvailability.WARMING_UP

        return FeatureAvailability.READY
