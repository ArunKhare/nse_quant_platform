from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

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
    proposal: TradeProposal | None
    opened_at: datetime
    closed_at: datetime | None = None
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
        self.last_closed_at: datetime | None = None

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
            proposal=proposal,
            opened_at=snapshot.ts.astimezone(UTC),
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
            # Never mark or exit a trade on its entry snapshot.
            if snapshot.ts <= trade.opened_at:
                continue

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

                exit_debit += price * leg.signed_quantity

            if complete:
                trade.exit_debit = exit_debit
                trade.realized_pnl = trade.entry_credit - exit_debit

    def close_position(
        self,
        trade: BacktestTrade,
        exit_reason: ExitReason,
        closed_at: datetime,
    ) -> None:
        trade.exit_reason = exit_reason
        trade.closed_at = closed_at.astimezone(UTC)

        self.cash += trade.realized_pnl
        self.closed_trades.append(trade)

        if trade in self.open_positions:
            self.open_positions.remove(trade)

        self.last_closed_at = trade.closed_at

    def can_enter(
        self,
        snapshot_ts: datetime,
        max_open_positions: int,
        cooldown_minutes: int,
    ) -> bool:
        if len(self.open_positions) >= max_open_positions:
            return False

        if self.last_closed_at is None:
            return True

        cooldown: timedelta = timedelta(minutes=cooldown_minutes)

        return snapshot_ts - self.last_closed_at >= cooldown

    def evaluate_exit(
        self,
        trade: BacktestTrade,
        features: MarketFeatures,
    ) -> ExitReason | None:
        proposal = trade.proposal

        if proposal is None:
            return None

        entry_credit = trade.entry_credit
        exit_value = trade.exit_debit

        target_price = proposal.target_price
        stop_loss_price = proposal.stop_loss_price

        if entry_credit > 0:
            # Net credit received at entry.
            if target_price is not None and exit_value <= target_price:
                return ExitReason.TARGET_PROFIT
            if stop_loss_price is not None and exit_value >= stop_loss_price:
                return ExitReason.STOP_LOSS
        else:
            # Net debit paid at entry.
            entry_debit = -entry_credit
            current_pnl = -exit_value - entry_debit

            if target_price is not None and current_pnl >= target_price:
                return ExitReason.TARGET_PROFIT

            if stop_loss_price is not None and current_pnl <= -stop_loss_price:
                return ExitReason.STOP_LOSS

        return None

    @staticmethod
    def _net_credit(legs: list[Leg]) -> float:
        credit = 0.0

        for leg in legs:
            if leg.entry_price is None:
                continue

            credit += leg.entry_price * leg.signed_quantity

        return credit
