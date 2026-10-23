"""Deterministic gates over multi-timeframe spot features."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from nse_quant.features.feature_service import SpotFeatureSnapshot


@dataclass(frozen=True)
class FeatureGateResult:
    passed: bool
    reasons: list[str]
    checks: dict[str, bool]


class SpotFeatureGate:
    def __init__(
        self,
        min_realized_vol: float = 0.0,
        max_realized_vol: float = 1.0,
        max_vwap_distance: float = 0.01,
        require_trend_alignment: bool = True,
        max_age_seconds: int = 300,
        index_symbols: tuple[str, ...] = (
            "NIFTY",
            "BANKNIFTY",
            "FINNIFTY",
            "MIDCPNIFTY",
        ),
    ) -> None:
        self._min_realized_vol = min_realized_vol
        self._max_realized_vol = max_realized_vol
        self._max_vwap_distance = max_vwap_distance
        self._require_trend_alignment = require_trend_alignment
        self._max_age_seconds = max_age_seconds
        self._index_symbols = set(index_symbols)

    def evaluate(
        self,
        snapshot: SpotFeatureSnapshot | None,
    ) -> FeatureGateResult:
        reasons: list[str] = []
        checks: dict[str, bool] = {}

        checks["feature_snapshot_available"] = snapshot is not None
        if snapshot is None:
            reasons.append("spot_features_unavailable")
            return FeatureGateResult(False, reasons, checks)

        age = datetime.now(UTC) - snapshot.ts.tz_convert(UTC)
        checks["feature_snapshot_fresh"] = (
            age <= timedelta(seconds=self._max_age_seconds)
        )

        if not checks["feature_snapshot_fresh"]:
            reasons.append("spot_features_stale")

        rv = snapshot.rv_1m_30
        if rv is not None and rv <=0:
            rv = None
        checks["realized_vol_available"] = rv is not None
        checks["realized_vol_in_range"] = (
            rv is not None
            and self._min_realized_vol <= rv <= self._max_realized_vol
        )
        if not checks["realized_vol_in_range"]:
            reasons.append("realized_vol_out_of_range")

        vwap_distance = snapshot.vwap_distance_1m

        is_index = snapshot.symbol in self._index_symbols
        checks["vwap_distance_applicable"] = not is_index

        if is_index:
            checks["vwap_distance_available"] = False
            checks["vwap_distance_acceptable"] = False
        else:
            checks["vwap_distance_available"] = vwap_distance is not None
            checks["vwap_distance_acceptable"] = (
                vwap_distance is not None
                and abs(vwap_distance) <= self._max_vwap_distance
            )

            if not checks["vwap_distance_acceptable"]:
                reasons.append("vwap_distance_excessive")

        trend_15m = snapshot.trend_15m
        trend_60m = snapshot.trend_60m

        checks["trend_context_available"] = (
            trend_15m is not None and trend_60m is not None
        )

        if self._require_trend_alignment:
            checks["trend_aligned"] = (
                trend_15m is not None
                and trend_60m is not None
                and (trend_15m >= 0) == (trend_60m >= 0)
            )
            if not checks["trend_aligned"]:
                reasons.append("multi_timeframe_trend_misaligned")
        else:
            checks["trend_aligned"] = True
            reasons.append("multi_timeframe_trend_context_unavailable")

        required_checks = {
            "feature_snapshot_available",
            "feature_snapshot_fresh",
            "realized_vol_in_range",
        }

        if checks["vwap_distance_applicable"]:
            required_checks.add("vwap_distance_acceptable")

        if self._require_trend_alignment:
            required_checks.add("trend_aligned")

        passed = all(
            value
            for key, value in checks.items()
            if key in required_checks
        )

        return FeatureGateResult(
            passed=passed,
            reasons=reasons,
            checks=checks,
        )