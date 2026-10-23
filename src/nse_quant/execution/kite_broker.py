"""Non-executing Kite broker skeleton.

Every mutating broker operation raises LiveTradingDisabledError. This class
must never place, modify, or cancel a live order in v0.3.0.
"""

from __future__ import annotations

from nse_quant.core.models import OrderStatus, PaperOrder, PaperPosition, TradeProposal
from nse_quant.execution.broker import BrokerInterface


class LiveTradingDisabledError(RuntimeError):
    """Raised when live order execution is attempted in a disabled milestone."""


class KiteBroker(BrokerInterface):
    """Structural Kite integration placeholder. It cannot execute orders."""

    def __init__(self, kite_client: object | None = None) -> None:
        self.kite_client = kite_client

    def submit(self, proposal: TradeProposal) -> PaperOrder:
        raise LiveTradingDisabledError(
            "Live Kite order placement is disabled in v0.3.0. Use PaperBroker."
        )

    def modify_order(self, order_id: str, payload: dict[str, object]) -> None:
        raise LiveTradingDisabledError("Live Kite order modification is disabled in v0.3.0.")

    def cancel_order(self, order_id: str) -> None:
        raise LiveTradingDisabledError("Live Kite order cancellation is disabled in v0.3.0.")

    def positions(self) -> list[PaperPosition]:
        raise LiveTradingDisabledError("Live Kite position access is disabled in v0.3.0.")

    def order_status(self, order_id: str) -> OrderStatus:
        raise LiveTradingDisabledError("Live Kite order-status access is disabled in v0.3.0.")
