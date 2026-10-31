"""Look-ahead-safe options-positioning evidence."""

from __future__ import annotations

import json
from typing import Any

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
        as_of = context.ts
        symbol = context.symbol

        current = self._summarize_snapshot(
            context.snapshot,
            features=context.features,
        )

        if not current["available"]:
            return {
                "available": False,
                "complete": False,
                "as_of": as_of.isoformat(),
                "symbol": symbol,
                "reason": current["reason"],
            }

        prior = self._latest_prior_snapshot(
            symbol=symbol,
            as_of=as_of,
        )

        pcr_change = (
            current["pcr"] - prior["pcr"]
            if prior and prior["pcr"] is not None and current["pcr"] is not None
            else None
        )

        call_oi_change = (
            current["call_oi"] - prior["call_oi"]
            if prior and prior["call_oi"] is not None
            else None
        )

        put_oi_change = (
            current["put_oi"] - prior["put_oi"] if prior and prior["put_oi"] is not None else None
        )

        atm_iv_change = (
            current["atm_iv"] - prior["atm_iv"]
            if prior and prior["atm_iv"] is not None and current["atm_iv"] is not None
            else None
        )

        expected_move_change = (
            current["expected_move"] - prior["expected_move"]
            if prior and prior["expected_move"] is not None and current["expected_move"] is not None
            else None
        )

        iv_crush_risk = self._is_iv_crush(
            prior_atm_iv=prior["atm_iv"] if prior else None,
            current_atm_iv=current["atm_iv"],
        )

        return {
            "available": True,
            "complete": prior is not None,
            "as_of": as_of.isoformat(),
            "symbol": symbol,
            "pcr": current["pcr"],
            "pcr_change": pcr_change,
            "call_oi": current["call_oi"],
            "put_oi": current["put_oi"],
            "call_oi_change": call_oi_change,
            "put_oi_change": put_oi_change,
            "atm_iv": current["atm_iv"],
            "atm_iv_change": atm_iv_change,
            "expected_move": current["expected_move"],
            "expected_move_change": expected_move_change,
            "iv_crush_risk": iv_crush_risk,
            "positioning_bias": self._positioning_bias(
                current["pcr"],
                self._settings.pcr_high_threshold,
                self._settings.pcr_low_threshold,
            ),
            "reason": None if prior is not None else "no_prior_snapshot",
        }

    def _latest_prior_snapshot(
        self,
        *,
        symbol: str,
        as_of: Any,
    ) -> dict[str, Any] | None:
        rows = self._store.conn.execute(
            """
            SELECT
                ts,
                payload_json
            FROM option_stream
            WHERE underlying = ?
              AND ts < ?
            ORDER BY ts DESC
            LIMIT 1
            """,
            [symbol, as_of],
        ).fetchall()

        if not rows:
            return None

        payload = json.loads(rows[0][1])
        return self._summarize_payload(payload)

    def _summarize_snapshot(
        self,
        snapshot: Any,
        *,
        features: Any,
    ) -> dict[str, Any]:
        if snapshot is None:
            return {
                "available": False,
                "reason": "missing_snapshot",
                "pcr": None,
                "call_oi": None,
                "put_oi": None,
                "atm_iv": None,
                "expected_move": None,
            }

        call_oi = 0
        put_oi = 0

        for quote in snapshot.quotes:
            if quote.instrument.option_type.value == "CE":
                call_oi += quote.oi or 0
            else:
                put_oi += quote.oi or 0

        pcr = put_oi / call_oi if call_oi > 0 else None

        return {
            "available": True,
            "reason": None,
            "pcr": pcr,
            "call_oi": call_oi,
            "put_oi": put_oi,
            "atm_iv": features.atm_iv,
            "expected_move": features.expected_move_points,
        }

    def _summarize_payload(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        call_oi = 0
        put_oi = 0

        for quote in payload.get("quotes", []):
            option_type = quote.get("instrument", {}).get("option_type")
            oi = quote.get("oi") or 0

            if option_type == "CE":
                call_oi += oi
            else:
                put_oi += oi

        pcr = put_oi / call_oi if call_oi > 0 else None

        return {
            "available": True,
            "reason": None,
            "pcr": pcr,
            "call_oi": call_oi,
            "put_oi": put_oi,
            "atm_iv": payload.get("atm_iv"),
            "expected_move": payload.get("expected_move"),
        }

    def _is_iv_crush(
        self,
        *,
        prior_atm_iv: float | None,
        current_atm_iv: float | None,
    ) -> bool:
        if prior_atm_iv is None or current_atm_iv is None:
            return False

        if prior_atm_iv <= 0:
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
