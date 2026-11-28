"""Observational institutional-regime components without trading gates."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime
from typing import Any

from nse_quant.core.constants import IST, REGULAR_SESSION_CLOSE
from nse_quant.core.models import ChainSnapshot, MarketFeatures
from nse_quant.core.regime_registry import is_canonical_regime_label
from nse_quant.core.settings import InstitutionalRegimeSettings
from nse_quant.research.evidence_plugins.base import (
    DecisionContext,
    EvidencePlugin,
)
from nse_quant.research.institutional_regime_price_action_v5 import (
    PRICE_ACTION_CLASSIFIER_VERSION,
    DailyBar,
    InstitutionalRegimePriceActionSettings,
    classify_daily_price_action,
)
from nse_quant.research.institutional_regime_skew import (
    InstitutionalRegimeSkewSettings,
    compute_skew,
)

HISTORY_SOURCE = "atm_average_live"


class InstitutionalRegimePlugin(EvidencePlugin):
    name = "institutional_regime"

    def __init__(
        self,
        *,
        store: Any,
        settings: InstitutionalRegimeSettings,
    ) -> None:
        self._store = store
        self._settings = settings
        self._skew_settings = InstitutionalRegimeSkewSettings()
        self._price_action_settings = InstitutionalRegimePriceActionSettings(
            daily_history_limit=settings.price_action_daily_history_limit,
            minimum_daily_bars=settings.price_action_minimum_daily_bars,
            confidence_floor=settings.price_action_confidence_floor,
        )

    def build(self, context: DecisionContext) -> dict[str, Any]:
        as_of = self._utc(context.ts)
        snapshot: ChainSnapshot | None = context.snapshot
        features: MarketFeatures | None = context.features

        if snapshot is None or features is None:
            return self._unavailable(
                context,
                as_of=as_of,
                reason="missing_current_inputs",
            )

        snapshot_ts = self._utc(snapshot.ts)
        feature_ts = self._utc(features.ts)

        if snapshot_ts > as_of or feature_ts > as_of:
            return self._unavailable(
                context,
                as_of=as_of,
                reason="future_current_input",
            )

        if (
            snapshot.underlying != context.symbol
            or features.underlying != context.symbol
            or features.expiry != snapshot.expiry
            or feature_ts != snapshot_ts
        ):
            return self._unavailable(
                context,
                as_of=as_of,
                reason="current_input_mismatch",
            )

        current_iv = features.atm_iv

        if current_iv is None or not math.isfinite(current_iv) or current_iv <= 0:
            return self._unavailable(
                context,
                as_of=as_of,
                reason="invalid_current_iv",
            )

        rows = self._store.conn.execute(
            """
            SELECT ts, iv
            FROM underlying_iv_observations
            WHERE underlying = ?
              AND expiry = ?
              AND source = ?
              AND ts < ?
              AND isfinite(iv)
              AND iv > 0
            ORDER BY ts DESC
            LIMIT ?
            """,
            [
                context.symbol,
                snapshot.expiry,
                HISTORY_SOURCE,
                snapshot_ts,
                self._settings.iv_history_limit,
            ],
        ).fetchall()

        history = [float(row[1]) for row in rows]
        history_count = len(history)

        iv_min = min(history) if history else None
        iv_max = max(history) if history else None

        raw_rank: float | None = None
        rank: float | None = None
        state: str | None = None

        if history_count < self._settings.min_iv_history_observations:
            iv_reason = "insufficient_iv_history"
        elif iv_min is None or iv_max is None or iv_max <= iv_min:
            iv_reason = "zero_iv_history_range"
        else:
            candidate = (current_iv - iv_min) / (iv_max - iv_min) * 100.0

            if not math.isfinite(candidate):
                iv_reason = "non_finite_iv_rank"
            else:
                raw_rank = candidate
                rank = max(0.0, min(100.0, candidate))
                state = "HIGH_IV" if rank >= self._settings.high_iv_rank_threshold else "NORMAL_IV"
                iv_reason = None

        iv_component = {
            "available": True,
            "complete": iv_reason is None,
            "state": state,
            "current_iv": current_iv,
            "current_iv_unit": "decimal",
            "current_input_ts": feature_ts.isoformat(),
            "history_source": HISTORY_SOURCE,
            "history_sampling": "persisted_observations_not_daily",
            "history_expiry": snapshot.expiry.isoformat(),
            "history_cutoff_exclusive": snapshot_ts.isoformat(),
            "history_limit": self._settings.iv_history_limit,
            "history_count": history_count,
            "minimum_history_count": (self._settings.min_iv_history_observations),
            "history_start_ts": (self._utc(rows[-1][0]).isoformat() if rows else None),
            "history_end_ts": (self._utc(rows[0][0]).isoformat() if rows else None),
            "iv_min": iv_min,
            "iv_max": iv_max,
            "iv_rank_raw": raw_rank,
            "iv_rank": rank,
            "iv_rank_unit": "percent",
            "high_iv_rank_threshold": (self._settings.high_iv_rank_threshold),
            "reason": iv_reason,
        }

        term_component = self._term_structure(
            symbol=context.symbol,
            near_expiry=snapshot.expiry,
            cutoff=snapshot_ts,
            as_of=as_of,
        )

        skew_component = self._skew(snapshot)
        price_action_component = self._price_action(context)

        components = {
            "iv_state": iv_component,
            "term_structure": term_component,
            "skew": skew_component,
            "price_action": price_action_component,
        }

        components_complete = all(component["complete"] for component in components.values())
        candidate_label = (
            "_".join(
                [
                    iv_component["state"],
                    term_component["state"],
                    skew_component["state"],
                    price_action_component["state"],
                ]
            )
            if components_complete
            else None
        )
        regime_label = (
            candidate_label if candidate_label is not None and is_canonical_regime_label(candidate_label) else None
        )
        all_complete = components_complete and regime_label is not None

        return {
            "available": True,
            "complete": all_complete,
            "thresholds_provisional": True,
            "decision_eligibility_asserted": False,
            "as_of": as_of.isoformat(),
            "symbol": context.symbol,
            "expiry": snapshot.expiry.isoformat(),
            "snapshot_ts": snapshot_ts.isoformat(),
            "classifier_version": "institutional_iv_term_components_v4_with_daily_price_action_v5",
            "price_action_classifier_version": PRICE_ACTION_CLASSIFIER_VERSION,
            "mode": "observation",
            "regime_label": regime_label,
            "components": components,
            "missing_components": (
                [name for name, component in components.items() if not component["complete"]]
                + (["canonical_regime_label"] if components_complete and regime_label is None else [])
            ),
            "reason": (
                None
                if all_complete
                else (
                    "non_canonical_composite_label"
                    if components_complete
                    else next(
                        (component["reason"] for component in components.values() if not component["complete"]),
                        "incomplete_components",
                    )
                )
            ),
        }

    def _skew(self, snapshot: ChainSnapshot) -> dict[str, Any]:
        if not snapshot.quotes:
            return {
                "available": False,
                "complete": False,
                "state": None,
                "reason": "no_option_quotes",
                "decision_eligibility_asserted": False,
            }

        atm_strike = snapshot.atm_strike()
        put_iv: float | None = None
        call_iv: float | None = None

        for quote in snapshot.quotes:
            if quote.instrument.expiry != snapshot.expiry:
                continue
            if quote.instrument.strike != atm_strike:
                continue
            if quote.iv is None or not math.isfinite(quote.iv) or quote.iv <= 0:
                continue
            if quote.instrument.option_type.value == "PE":
                put_iv = quote.iv
            elif quote.instrument.option_type.value == "CE":
                call_iv = quote.iv

        return compute_skew(
            put_iv=put_iv,
            call_iv=call_iv,
            settings=self._skew_settings,
        )

    def _price_action(self, context: DecisionContext) -> dict[str, Any]:
        token = getattr(context, "spot_instrument_token", None)
        if token is None:
            return {
                "available": False,
                "complete": False,
                "state": None,
                "reason": "missing_spot_instrument_token",
                "classifier_version": PRICE_ACTION_CLASSIFIER_VERSION,
                "decision_eligibility_asserted": False,
            }

        # Daily bars are timestamped at the session date. Exclude the current
        # IST calendar date unconditionally so a partially aggregated daily bar
        # can never enter the classifier, including after the close.
        cutoff_date = self._utc(context.ts).astimezone(IST).date()
        rows = self._store.conn.execute(
            """
            SELECT CAST(ts AT TIME ZONE 'Asia/Kolkata' AS DATE), open, high, low, close, volume
            FROM spot_candles
            WHERE instrument_token = ?
              AND interval = 'day'
              AND CAST(ts AT TIME ZONE 'Asia/Kolkata' AS DATE) < ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            [
                token,
                cutoff_date,
                self._price_action_settings.daily_history_limit,
            ],
        ).fetchall()

        if not rows:
            return {
                "available": False,
                "complete": False,
                "state": None,
                "reason": "no_completed_daily_history",
                "classifier_version": PRICE_ACTION_CLASSIFIER_VERSION,
                "decision_eligibility_asserted": False,
            }

        bars = [
            DailyBar(
                trade_date=row[0],
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5] or 0.0),
            )
            for row in reversed(rows)
        ]
        result = classify_daily_price_action(bars, self._price_action_settings)
        result["source"] = "spot_candles.day"
        result["bar_cutoff_exclusive"] = cutoff_date.isoformat()
        result["bar_completion_policy"] = "exclude_current_ist_calendar_date"
        result["instrument_token"] = token
        return result

    def _term_structure(
        self,
        *,
        symbol: str,
        near_expiry: date,
        cutoff: datetime,
        as_of: datetime,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "available": False,
            "complete": False,
            "state": None,
            "source": HISTORY_SOURCE,
            "pair_selection": "nearest_persisted_deferred_expiry",
            "near_expiry": near_expiry.isoformat(),
            "deferred_expiry": None,
            "observation_cutoff_inclusive": cutoff.isoformat(),
            "near_observation_ts": None,
            "deferred_observation_ts": None,
            "near_age_seconds": None,
            "deferred_age_seconds": None,
            "observation_gap_seconds": None,
            "near_atm_iv": None,
            "deferred_atm_iv": None,
            "iv_difference": None,
            "iv_difference_unit": "decimal",
            "tolerance": self._settings.term_structure_tolerance,
            "max_age_seconds": (self._settings.max_term_observation_age_seconds),
            "max_gap_seconds": (self._settings.max_term_observation_gap_seconds),
            "reason": None,
        }

        near_expiry_close = datetime.combine(
            near_expiry,
            REGULAR_SESSION_CLOSE,
            tzinfo=IST,
        ).astimezone(UTC)

        if as_of >= near_expiry_close:
            result["reason"] = "expired_near_expiry"
            return result

        rows = self._store.conn.execute(
            """
            WITH latest_per_expiry AS (
                SELECT
                    expiry,
                    ts,
                    iv,
                    ROW_NUMBER() OVER (
                        PARTITION BY expiry
                        ORDER BY ts DESC
                    ) AS observation_rank
                FROM underlying_iv_observations
                WHERE underlying = ?
                  AND source = ?
                  AND expiry >= ?
                  AND ts <= ?
            )
            SELECT expiry, ts, iv
            FROM latest_per_expiry
            WHERE observation_rank = 1
            ORDER BY expiry
            LIMIT 2
            """,
            [
                symbol,
                HISTORY_SOURCE,
                near_expiry,
                cutoff,
            ],
        ).fetchall()

        if not rows or rows[0][0] != near_expiry:
            result["reason"] = "missing_near_observation"
            return result

        near_row = rows[0]
        near_ts = self._utc(near_row[1])
        near_iv = float(near_row[2])

        result["near_observation_ts"] = near_ts.isoformat()
        result["near_age_seconds"] = (as_of - near_ts).total_seconds()

        if math.isfinite(near_iv) and near_iv > 0:
            result["near_atm_iv"] = near_iv
        else:
            result["reason"] = "invalid_near_iv"
            return result

        if len(rows) < 2:
            result["reason"] = "missing_deferred_observation"
            return result

        deferred_row = rows[1]
        deferred_ts = self._utc(deferred_row[1])
        deferred_iv = float(deferred_row[2])

        result["deferred_expiry"] = deferred_row[0].isoformat()
        result["deferred_observation_ts"] = deferred_ts.isoformat()
        result["deferred_age_seconds"] = (as_of - deferred_ts).total_seconds()
        result["observation_gap_seconds"] = abs((near_ts - deferred_ts).total_seconds())

        if math.isfinite(deferred_iv) and deferred_iv > 0:
            result["deferred_atm_iv"] = deferred_iv
        else:
            result["reason"] = "invalid_deferred_iv"
            return result

        result["available"] = True

        if near_ts > cutoff or deferred_ts > cutoff:
            result["reason"] = "future_term_observation"
            return result

        near_age = float(result["near_age_seconds"])
        deferred_age = float(result["deferred_age_seconds"])

        if near_age < 0 or deferred_age < 0:
            result["reason"] = "future_term_observation"
            return result

        max_age = self._settings.max_term_observation_age_seconds

        if near_age > max_age or deferred_age > max_age:
            result["reason"] = "stale_term_observation"
            return result

        if result["observation_gap_seconds"] > self._settings.max_term_observation_gap_seconds:
            result["reason"] = "term_observation_gap_exceeded"
            return result

        difference = deferred_iv - near_iv
        tolerance = self._settings.term_structure_tolerance

        result["iv_difference"] = difference
        result["state"] = (
            "CONTANGO" if difference > tolerance else "BACKWARDATION" if difference < -tolerance else "FLAT"
        )
        result["complete"] = True

        return result

    def _unavailable(
        self,
        context: DecisionContext,
        *,
        as_of: datetime,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "available": False,
            "complete": False,
            "thresholds_provisional": True,
            "decision_eligibility_asserted": False,
            "as_of": as_of.isoformat(),
            "symbol": context.symbol,
            "classifier_version": "institutional_iv_term_components_v4_with_daily_price_action_v5",
            "price_action_classifier_version": PRICE_ACTION_CLASSIFIER_VERSION,
            "mode": "observation",
            "regime_label": None,
            "components": {
                "iv_state": {
                    "available": False,
                    "complete": False,
                    "state": None,
                    "reason": reason,
                },
                "skew": {
                    "available": False,
                    "complete": False,
                    "state": None,
                    "reason": reason,
                },
                "price_action": {
                    "available": False,
                    "complete": False,
                    "state": None,
                    "reason": reason,
                    "classifier_version": PRICE_ACTION_CLASSIFIER_VERSION,
                    "decision_eligibility_asserted": False,
                },
                "term_structure": {
                    "available": False,
                    "complete": False,
                    "state": None,
                    "reason": reason,
                },
            },
            "missing_components": [
                "iv_state",
                "term_structure",
                "skew",
                "price_action",
            ],
            "reason": reason,
        }

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Institutional regime requires timezone-aware timestamps")

        return value.astimezone(UTC)
