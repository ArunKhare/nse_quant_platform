"""Cash-stock swing strategy: proposal-only, paper-mode ready.

Consumes the research signal from nse_quant.research.cash_stock_swing and
emits a TradeProposal. Never submits, modifies, or cancels an order.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from nse_quant.core.models import (
    GateResult,
    Instrument,
    Leg,
    OrderSide,
    TradeProposal,
)
from nse_quant.core.settings import get_settings
from nse_quant.research.cash_stock_swing import (
    CashStockSwingSettings,
    generate_signal,
)


class CashStockSwingStrategy:
    """Evaluate daily candles and produce a cash-stock swing TradeProposal."""

    strategy_name = "cash_stock_swing"

    def __init__(self, settings: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self.signal_settings = CashStockSwingSettings()

    def evaluate(
        self,
        candles: list[dict[str, Any]],
        event_risk_active: bool = False,
        symbol: str = "UNKNOWN",
    ) -> tuple[TradeProposal | None, list[GateResult]]:
        import pandas as pd

        if not candles:
            return None, []

        frame = pd.DataFrame(candles)
        signal = generate_signal(
            candles=frame,
            settings=self.signal_settings,
            event_risk_active=event_risk_active,
        )

        gates: list[GateResult] = []

        if not signal.get("available") or not signal.get("entry_signal"):
            gates.append(
                GateResult(
                    gate="cash_stock_swing_entry",
                    passed=False,
                    reason="no_entry_signal",
                    details=signal,
                )
            )
            return None, gates

        entry = float(signal["entry_price"])
        stop = float(signal["stop_price"])
        target = float(signal["target_price"])

        gates.append(
            GateResult(
                gate="cash_stock_swing_entry",
                passed=True,
                reason="entry_signal",
                details=signal,
            )
        )

        # Use a synthetic Instrument placeholder; in production this should be
        # resolved from the actual instrument master.
        instrument = Instrument(
            instrument_token=0,
            tradingsymbol=symbol,
            strike=0.0,
            option_type=None,
            expiry=None,
        )

        proposal = TradeProposal(
            strategy=self.strategy_name,
            underlying=symbol,
            expiry=date.today(),
            thesis="Cash-stock swing trend-following entry.",
            legs=[
                Leg(
                    instrument=instrument,
                    side=OrderSide.BUY,
                    lots=1,
                    entry_price=entry,
                )
            ],
            entry_limit_price=entry,
            target_price=target,
            stop_loss_price=stop,
            expected_move_points=None,
            metadata={
                "signal": signal,
                "time_stop_days": self.signal_settings.time_stop_days,
            },
        )

        return proposal, gates
