"""Look-ahead-safe options-positioning evidence."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from nse_quant.core.models import ChainSnapshot, MarketFeatures
from nse_quant.research.evidence_plugins.base import (
    DecisionContext,
    EvidencePlugin,
)


class OptionPositioningPlugin(EvidencePlugin):
    name = "option_positioning"

    def __init__(
        self,
        *,
        store: Any,
        settings: Any,
    ) -> None:
        self._store = store
        self._settings = settings

    def build(self, context: DecisionContext) -> dict[str, Any]:
        snapshot: ChainSnapshot | None = context.snapshot

        if snapshot is None:
            return {
                "available": False,
                "complete": False,
                "as_of": context.ts.isoformat(),
                "symbol": context.symbol,
                "reason": "missing_snapshot",
            }

        features: MarketFeatures = context.features

        if snapshot.ts > context.ts or features.ts > context.ts:
            return {
                "available": False,
                "complete": False,
                "as_of": context.ts.isoformat(),
                "symbol": context.symbol,
                "reason": "future_current_input",
            }

        if (
            snapshot.underlying != context.symbol
            or features.underlying != context.symbol
            or features.expiry != snapshot.expiry
            or features.ts != snapshot.ts
        ):
            return {
                "available": False,
                "complete": False,
                "as_of": context.ts.isoformat(),
                "symbol": context.symbol,
                "reason": "current_input_mismatch",
            }

        current = self._summarize_snapshot(
            snapshot,
            features=features,
        )

        prior = self._latest_prior_snapshot(
            symbol=context.symbol,
            expiry=snapshot.expiry,
            as_of=snapshot.ts,
        )

        comparison_fields = (
            "pcr",
            "call_oi",
            "put_oi",
            "atm_iv",
            "expected_move",
        )

        changes = {
            field: self._change(
                current[field],
                prior[field] if prior is not None else None,
            )
            for field in comparison_fields
        }

        missing_inputs = [
            f"current.{field}" for field in comparison_fields if current[field] is None
        ]

        if prior is None:
            missing_inputs.append("prior_snapshot")
        else:
            missing_inputs.extend(
                f"prior.{field}" for field in comparison_fields if prior[field] is None
            )

        complete = not missing_inputs

        prior_atm_iv = prior["atm_iv"] if prior is not None else None
        iv_crush_available = (
            current["atm_iv"] is not None and prior_atm_iv is not None and prior_atm_iv > 0
        )

        return {
            "available": True,
            "complete": complete,
            "as_of": context.ts.isoformat(),
            "symbol": context.symbol,
            "expiry": snapshot.expiry.isoformat(),
            "current_snapshot_ts": snapshot.ts.isoformat(),
            "prior_snapshot_ts": (prior["ts"].isoformat() if prior is not None else None),
            "prior_run_id": (prior["run_id"] if prior is not None else None),
            "pcr": current["pcr"],
            "pcr_change": changes["pcr"],
            "call_oi": current["call_oi"],
            "put_oi": current["put_oi"],
            "call_oi_change": changes["call_oi"],
            "put_oi_change": changes["put_oi"],
            "atm_iv": current["atm_iv"],
            "atm_iv_change": changes["atm_iv"],
            "expected_move": current["expected_move"],
            "expected_move_change": changes["expected_move"],
            "expected_move_unit": "points",
            "iv_crush_available": iv_crush_available,
            "iv_crush_risk": self._is_iv_crush(
                prior_atm_iv=prior_atm_iv,
                current_atm_iv=current["atm_iv"],
            ),
            "positioning_bias": self._positioning_bias(
                current["pcr"],
                self._settings.pcr_high_threshold,
                self._settings.pcr_low_threshold,
            ),
            "missing_inputs": missing_inputs,
            "reason": (
                "no_prior_snapshot"
                if prior is None
                else None
                if complete
                else "incomplete_comparison_inputs"
            ),
        }

    def _latest_prior_snapshot(
        self,
        *,
        symbol: str,
        expiry: date,
        as_of: datetime,
    ) -> dict[str, Any] | None:
        rows = self._store.conn.execute(
            """
            WITH prior_snapshot AS (
                SELECT run_id, ts
                FROM option_stream
                WHERE underlying = ?
                  AND expiry = ?
                  AND ts < ?
                GROUP BY run_id, ts
                ORDER BY ts DESC, run_id DESC
                LIMIT 1
            )
            SELECT
                stream.run_id,
                stream.ts,
                stream.option_type,
                stream.oi,
                features.atm_iv,
                features.expected_move_points
            FROM option_stream AS stream
            INNER JOIN prior_snapshot AS prior
                ON stream.run_id = prior.run_id
               AND stream.ts = prior.ts
            LEFT JOIN feature_snapshots AS features
                ON features.run_id = stream.run_id
               AND features.ts = stream.ts
               AND features.underlying = stream.underlying
               AND features.expiry = stream.expiry
            WHERE stream.underlying = ?
              AND stream.expiry = ?
            ORDER BY stream.instrument_token
            """,
            [symbol, expiry, as_of, symbol, expiry],
        ).fetchall()

        if not rows:
            return None

        call_oi = self._total_oi([row[3] for row in rows if row[2] == "CE"])
        put_oi = self._total_oi([row[3] for row in rows if row[2] == "PE"])

        return {
            "run_id": rows[0][0],
            "ts": rows[0][1],
            "call_oi": call_oi,
            "put_oi": put_oi,
            "pcr": self._pcr(call_oi, put_oi),
            "atm_iv": rows[0][4],
            "expected_move": rows[0][5],
        }

    def _summarize_snapshot(
        self,
        snapshot: ChainSnapshot,
        *,
        features: MarketFeatures,
    ) -> dict[str, Any]:
        quotes = [quote for quote in snapshot.quotes if quote.instrument.expiry == snapshot.expiry]

        call_oi = self._total_oi(
            [quote.oi for quote in quotes if quote.instrument.option_type.value == "CE"]
        )
        put_oi = self._total_oi(
            [quote.oi for quote in quotes if quote.instrument.option_type.value == "PE"]
        )

        return {
            "call_oi": call_oi,
            "put_oi": put_oi,
            "pcr": self._pcr(call_oi, put_oi),
            "atm_iv": features.atm_iv,
            "expected_move": features.expected_move_points,
        }

    @staticmethod
    def _total_oi(values: list[int | None]) -> int | None:
        if not values or any(value is None or value < 0 for value in values):
            return None

        return sum(value for value in values if value is not None)

    @staticmethod
    def _pcr(
        call_oi: int | None,
        put_oi: int | None,
    ) -> float | None:
        if call_oi is None or put_oi is None or call_oi <= 0:
            return None

        return put_oi / call_oi

    @staticmethod
    def _change(
        current: float | int | None,
        prior: float | int | None,
    ) -> float | int | None:
        if current is None or prior is None:
            return None

        return current - prior

    def _is_iv_crush(
        self,
        *,
        prior_atm_iv: float | None,
        current_atm_iv: float | None,
    ) -> bool:
        if prior_atm_iv is None or current_atm_iv is None or prior_atm_iv <= 0:
            return False

        decline_pct = (prior_atm_iv - current_atm_iv) / prior_atm_iv * 100

        return decline_pct >= self._settings.iv_crush_decline_pct

    @staticmethod
    def _positioning_bias(
        pcr: float | None,
        high_threshold: float,
        low_threshold: float,
    ) -> str | None:
        if pcr is None:
            return None

        if pcr >= high_threshold:
            return "PUT_SKEWED"

        if pcr <= low_threshold:
            return "CALL_SKEWED"

        return "BALANCED"
