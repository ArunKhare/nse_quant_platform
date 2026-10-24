from __future__ import annotations

from dataclasses import dataclass, field

from nse_quant.core.models import (
    ChainSnapshot,
    ExitReason,
    Leg,
    MarketFeatures,
    OrderSide,
    TradeProposal,
)


@dataclass
class BacktestTrade:
    strategy_position_id: str
    proposal_id: str
    opened_at: object
    closed_at: object | None = None
    entry_credit: float = 0.0
    exit_debit: float = 0.0
    realized_pnl: float = 0.0
    exit_reason: ExitReason | None = None
    legs: list[Leg] = field(default_factory=list)


class BacktestPortfolio:
    def __init__(self, initial_capital: float) -> None:
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.open_positions: list[BacktestTrade] = []
        self.closed_trades: list[BacktestTrade] = []

    def open_position(
        self,
        proposal: TradeProposal,
        snapshot: ChainSnapshot,
        slippage_pct: float,
    ) -> BacktestTrade:
        filled_legs: list[Leg] = []

        for leg in proposal.legs:
            entry_price = leg.entry_price

            if entry_price is None:
                continue

            if leg.side == OrderSide.BUY:
                entry_price *= 1 + slippage_pct
            else:
                entry_price *= 1 - slippage_pct

            filled_legs.append(leg.model_copy(update={"entry_price": entry_price}))

        entry_credit = self._net_credit(filled_legs)

        trade = BacktestTrade(
            strategy_position_id=proposal.proposal_id,
            proposal_id=proposal.proposal_id,
            opened_at=snapshot.ts,
            entry_credit=entry_credit,
            legs=filled_legs,
        )

        self.open_positions.append(trade)
        self.cash += entry_credit

        return trade

    def mark_to_market(
        self,
        snapshot: ChainSnapshot,
        features: MarketFeatures,
    ) -> None:
        quote_lookup = {
            (quote.instrument.option_type.value, quote.instrument.strike): quote
            for quote in snapshot.quotes
        }

        for trade in self.open_positions:
            exit_debit = 0.0
            complete = True

            for leg in trade.legs:
                quote = quote_lookup.get(
                    (
                        leg.instrument.option_type.value,
                        leg.instrument.strike,
                    )
                )

                if quote is None:
                    complete = False
                    continue

                price = quote.mid or quote.ltp

                if price is None:
                    complete = False
                    continue

                signed_quantity = leg.signed_quantity
                exit_debit += price * signed_quantity

            if complete:
                trade.exit_debit = exit_debit
                trade.realized_pnl = trade.entry_credit - exit_debit

    def close_positions(self) -> list[BacktestTrade]:
        closed: list[BacktestTrade] = []

        for trade in self.open_positions:
            if trade.realized_pnl >= 0:
                trade.exit_reason = ExitReason.TARGET_PROFIT
            else:
                trade.exit_reason = ExitReason.STOP_LOSS

            trade.closed_at = trade.opened_at
            self.cash += trade.realized_pnl
            closed.append(trade)

        self.open_positions = []
        self.closed_trades.extend(closed)

        return closed

    @staticmethod
    def _net_credit(legs: list[Leg]) -> float:
        credit = 0.0

        for leg in legs:
            if leg.entry_price is None:
                continue

            credit += leg.entry_price * leg.signed_quantity

        return credit
