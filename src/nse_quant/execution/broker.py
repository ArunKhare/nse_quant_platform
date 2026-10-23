"""Broker abstraction and paper broker."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from nse_quant.core.models import (
    OrderSide,
    OrderStatus,
    PaperOrder,
    PaperPosition,
    TradeProposal,
)


class BrokerInterface:
    """Execution boundary for order-capable brokers."""

    def submit(self, proposal: TradeProposal) -> PaperOrder:
        raise NotImplementedError

    def positions(self) -> list[PaperPosition]:
        raise NotImplementedError


class PaperBroker(BrokerInterface):
    """Executable paper broker.

    It fills proposals at their proposed limit price and maintains independent
    per-leg entry and current prices for correct P&L attribution.
    """

    def __init__(self) -> None:
        self.orders: list[PaperOrder] = []
        self._positions: list[PaperPosition] = []

    def submit(self, proposal: TradeProposal) -> PaperOrder:
        order = PaperOrder(
            proposal_id=proposal.proposal_id,
            strategy=proposal.strategy,
            legs=proposal.legs,
            limit_price=proposal.entry_limit_price,
            status=OrderStatus.SUBMITTED,
        )

        if proposal.entry_limit_price <= 0:
            order.status = OrderStatus.REJECTED
            order.reject_reason = "invalid_price"
            self.orders.append(order)
            return order

        filled_at = datetime.now(UTC)
        order.status = OrderStatus.FILLED
        order.filled_price = proposal.entry_limit_price
        order.filled_at = filled_at

        leg_entry_prices = {
            leg.instrument.instrument_token: self._initial_leg_price(proposal, leg)
            for leg in proposal.legs
        }

        position = PaperPosition(
            proposal_id=proposal.proposal_id,
            strategy=proposal.strategy,
            opened_at=filled_at,
            legs=proposal.legs,
            entry_price=proposal.entry_limit_price,
            current_price=proposal.entry_limit_price,
            thesis=proposal.thesis,
            leg_entry_prices=leg_entry_prices,
            leg_current_prices=dict(leg_entry_prices),
        )

        self._positions.append(position)
        self.orders.append(order)
        return order

    def positions(self) -> list[PaperPosition]:
        return list(self._positions)

    def mark_position(
        self,
        position_id: str,
        leg_current_prices: dict[int, float],
    ) -> PaperPosition | None:
        """Mark a position using one current price per instrument token."""
        position = self._get_open_position(position_id)

        if position is None:
            return None

        position.leg_current_prices.update(leg_current_prices)
        position.current_price = self._strategy_mark(position)
        position.unrealized_pnl = self._strategy_pnl(
            position,
            position.leg_current_prices,
        )

        return position

    def close_position(
        self,
        position_id: str,
        leg_exit_prices: dict[int, float],
        reason: str,
    ) -> PaperPosition | None:
        """Close a position using one exit price per instrument token."""
        position = self._get_open_position(position_id)

        if position is None:
            return None

        position.leg_current_prices.update(leg_exit_prices)
        position.current_price = self._strategy_mark(position)
        position.realized_pnl = self._strategy_pnl(
            position,
            position.leg_current_prices,
        )
        position.unrealized_pnl = 0.0
        position.status = "CLOSED"
        position.exit_reason = reason
        position.closed_at = datetime.now(UTC)
        position.thesis_status = "VALID" if position.realized_pnl >= 0 else "INVALID"

        return position

    def _get_open_position(self, position_id: str) -> PaperPosition | None:
        for position in self._positions:
            if position.position_id == position_id and position.status == "OPEN":
                return position

        return None

    @staticmethod
    def _initial_leg_price(
        proposal: TradeProposal,
        leg: Any,
    ) -> float:
        """Use an equal premium allocation until leg-level fills are available."""
        leg_count = len(proposal.legs)
        return proposal.entry_limit_price / leg_count if leg_count else 0.0

    @staticmethod
    def _leg_pnl(
        position: PaperPosition,
        instrument_token: int,
        current_price: float,
    ) -> float:
        leg = next(
            (
                item
                for item in position.legs
                if item.instrument.instrument_token == instrument_token
            ),
            None,
        )

        if leg is None:
            return 0.0

        entry_price = position.leg_entry_prices.get(instrument_token, 0.0)
        direction = 1 if leg.side == OrderSide.BUY else -1

        return (current_price - entry_price) * leg.quantity * direction

    def _strategy_pnl(
        self,
        position: PaperPosition,
        current_prices: dict[int, float],
    ) -> float:
        return sum(self._leg_pnl(position, token, price) for token, price in current_prices.items())

    def _strategy_mark(self, position: PaperPosition) -> float:
        """Net premium value of the strategy group at current leg prices."""
        net_value = 0.0

        for leg in position.legs:
            price = position.leg_current_prices.get(
                leg.instrument.instrument_token,
                position.leg_entry_prices.get(
                    leg.instrument.instrument_token,
                    0.0,
                ),
            )
            direction = 1 if leg.side == OrderSide.BUY else -1
            net_value += price * leg.quantity * direction

        return net_value
