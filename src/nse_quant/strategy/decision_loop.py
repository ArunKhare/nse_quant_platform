"""Paper decision loop: market data to post-trade review.

Flow:
market data -> analytics -> feature snapshot -> strategy proposal -> gates
-> risk check -> paper order -> independent leg positions -> marking/P&L
-> exit evaluation -> close -> post-trade review.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from nse_quant.analytics.features import build_features
from nse_quant.core.models import (
    ChainSnapshot,
    MarketFeatures,
    OptionQuote,
    OrderSide,
    PaperOrder,
    StrategyPosition,
    TradeProposal,
)
from nse_quant.core.settings import get_settings
from nse_quant.execution.broker import PaperBroker
from nse_quant.features.feature_store import FeatureStore
from nse_quant.persistence.repositories import (
    DecisionRepository,
    PositionRepository,
)
from nse_quant.risk.risk_engine import RiskEngine
from nse_quant.strategy.exit_engine import ExitEngine
from nse_quant.strategy.iron_condor import IronCondorMonitor


class DecisionLoop:
    def __init__(
        self,
        store: Any,
        provider: Any,
        broker: PaperBroker,
        run_id: str,
        settings: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.store = store
        self.provider = provider
        self.broker = broker
        self.run_id = run_id

        self.feature_store = FeatureStore(store.conn)
        self.decisions = DecisionRepository(store.conn)
        self.positions = PositionRepository(store.conn)
        self.risk = RiskEngine(store.conn, self.settings, self.positions)
        self.exit_engine = ExitEngine(self.settings)
        self.strategy = IronCondorMonitor(self.settings)

    def run_once(self) -> dict[str, Any]:
        snapshot = self.provider.get_chain_snapshot()
        features = self._build_features(snapshot)

        self.feature_store.save(self.run_id, features)
        self.decisions.save_decision(
            self.run_id,
            "feature_snapshot",
            None,
            features.model_dump(mode="json"),
        )

        proposal, gates = self.strategy.evaluate(snapshot, features)
        self.decisions.save_gate_results(
            self.run_id,
            proposal,
            gates,
        ) if proposal else None

        if proposal is None:
            self.decisions.save_decision(
                self.run_id,
                "no_proposal",
                None,
                {"gates": [gate.model_dump(mode="json") for gate in gates]},
            )
            return {"status": "no_proposal"}

        self.decisions.save_decision(
            self.run_id,
            "signal",
            proposal,
            {
                "gates": [gate.model_dump(mode="json") for gate in gates],
                "proposal": proposal.model_dump(mode="json"),
            },
        )

        quote_lookup = self._quote_lookup(snapshot)
        risk_decision = self.risk.evaluate(proposal, features, quote_lookup)

        self.decisions.save_risk_decision(
            self.run_id,
            proposal,
            risk_decision,
        )

        if not risk_decision.approved:
            return {
                "status": "risk_rejected",
                "proposal_id": proposal.proposal_id,
                "reasons": risk_decision.reasons,
            }

        if self.settings.safety.dry_run or not self.settings.safety.trading_enabled:
            self.decisions.save_decision(
                self.run_id,
                "dry_run_order_skipped",
                proposal,
                {"would_submit": True},
            )
            return {
                "status": "dry_run",
                "proposal_id": proposal.proposal_id,
            }

        order = self.broker.submit(proposal)
        self._persist_order(order)

        if order.status.value != "FILLED":
            return {
                "status": order.status.value,
                "proposal_id": proposal.proposal_id,
                "reason": order.reject_reason,
            }

        strategy_position, leg_positions = self._open_positions(
            proposal,
            order,
        )

        self._mark_positions(
            proposal,
            strategy_position,
            leg_positions,
            snapshot,
        )

        exit_evaluation = self.exit_engine.evaluate(
            proposal,
            strategy_position,
            leg_positions,
            features,
            kill_switch_active=False,
            risk_breached=False,
            data_stale=False,
        )

        self.positions.save_exit_evaluation(exit_evaluation)

        if exit_evaluation.selected_reason is not None:
            self._close_positions(
                proposal,
                strategy_position,
                leg_positions,
                exit_evaluation.selected_reason,
            )

        return {
            "status": "paper_filled",
            "proposal_id": proposal.proposal_id,
            "strategy_position_id": strategy_position.strategy_position_id,
            "exit_reason": (
                exit_evaluation.selected_reason.value
                if exit_evaluation.selected_reason
                else None
            ),
        }

    def _build_features(self, snapshot: ChainSnapshot) -> MarketFeatures:
        iv_history = self.store.latest_iv_history(snapshot.underlying)
        spot_history = [snapshot.spot] * 30

        return build_features(snapshot, iv_history, spot_history)

    @staticmethod
    def _quote_lookup(
        snapshot: ChainSnapshot,
    ) -> dict[tuple[str, float], OptionQuote]:
        return {
            (quote.instrument.option_type.value, quote.instrument.strike): quote
            for quote in snapshot.quotes
        }

    def _persist_order(self, order: PaperOrder) -> None:
        self.store.conn.execute(
            """
            INSERT OR REPLACE INTO orders VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                order.order_id,
                datetime.now(UTC),
                self.run_id,
                order.proposal_id,
                order.strategy,
                "PaperBroker",
                order.status.value,
                order.limit_price,
                order.filled_price,
                order.filled_at,
                order.reject_reason,
                order.model_dump_json(),
            ],
        )

    def _open_positions(
        self,
        proposal: TradeProposal,
        order: PaperOrder,
    ) -> tuple[StrategyPosition, list[Any]]:
        filled_at = order.filled_at or datetime.now(UTC)
        entry_price = order.filled_price or proposal.entry_limit_price

        strategy_position = StrategyPosition(
            proposal_id=proposal.proposal_id,
            strategy=proposal.strategy,
            underlying=proposal.underlying,
            expiry=proposal.expiry,
            opened_at=filled_at,
            entry_price=entry_price,
            current_price=entry_price,
            thesis=proposal.thesis,
            metadata=proposal.metadata,
        )

        self.positions.create_strategy_position(strategy_position)

        leg_positions = []

        for leg in proposal.legs:
            leg_position = type(leg)(
                leg_position_id=f"{strategy_position.strategy_position_id}:{leg.instrument.tradingsymbol}",
                strategy_position_id=strategy_position.strategy_position_id,
                proposal_id=proposal.proposal_id,
                strategy=proposal.strategy,
                instrument=leg.instrument,
                side=leg.side,
                lots=leg.lots,
                opened_at=filled_at,
                entry_price=proposal.entry_limit_price / len(proposal.legs),
                current_price=proposal.entry_limit_price / len(proposal.legs),
            )

            self.positions.create_leg_position(leg_position)
            leg_positions.append(leg_position)

        return strategy_position, leg_positions

    def _mark_positions(
        self,
        proposal: TradeProposal,
        strategy_position: StrategyPosition,
        leg_positions: list[Any],
        snapshot: ChainSnapshot,
    ) -> None:
        quote_lookup = self._quote_lookup(snapshot)
        strategy_mark = 0.0

        for leg_position in leg_positions:
            quote = quote_lookup.get(
                (
                    leg_position.instrument.option_type.value,
                    leg_position.instrument.strike,
                )
            )

            mark = self._mark_price(quote)

            if mark is None:
                mark = leg_position.current_price or leg_position.entry_price

            leg_position.current_price = mark

            direction = 1 if leg_position.side == OrderSide.BUY else -1
            leg_position.unrealized_pnl = (
                mark - leg_position.entry_price
            ) * leg_position.quantity * direction

            self.positions.update_leg_position(leg_position)

            strategy_mark += (
                mark
                * leg_position.quantity
                * (1 if leg_position.side == OrderSide.BUY else -1)
            )

        strategy_position.current_price = strategy_mark
        strategy_position.unrealized_pnl = (
            strategy_position.entry_price - strategy_mark
        )

        self.positions.update_strategy_position(strategy_position)

    @staticmethod
    def _mark_price(quote: OptionQuote | None) -> float | None:
        if quote is None:
            return None

        if quote.bid is not None and quote.ask is not None and quote.ask >= quote.bid > 0:
            return (quote.bid + quote.ask) / 2

        return quote.ltp

    def _close_positions(
        self,
        proposal: TradeProposal,
        strategy_position: StrategyPosition,
        leg_positions: list[Any],
        exit_reason: Any,
    ) -> None:
        closed_at = datetime.now(UTC)

        strategy_position.status = "CLOSED"
        strategy_position.closed_at = closed_at
        strategy_position.exit_reason = exit_reason
        strategy_position.realized_pnl = strategy_position.unrealized_pnl
        strategy_position.unrealized_pnl = 0.0

        self.positions.update_strategy_position(strategy_position)

        for leg_position in leg_positions:
            leg_position.status = "CLOSED"
            leg_position.closed_at = closed_at
            leg_position.exit_reason = exit_reason
            leg_position.realized_pnl = leg_position.unrealized_pnl
            leg_position.unrealized_pnl = 0.0

            self.positions.update_leg_position(leg_position)

        from nse_quant.core.models import PostTradeReview

        review = PostTradeReview(
            strategy_position_id=strategy_position.strategy_position_id,
            proposal_id=proposal.proposal_id,
            strategy=proposal.strategy,
            closed_at=closed_at,
            realized_pnl=strategy_position.realized_pnl,
            exit_reason=exit_reason,
            thesis_status="VALID" if strategy_position.realized_pnl >= 0 else "INVALID",
            decision_quality_notes="Thesis and gate evidence retained in decision history.",
            outcome_notes="Realized P&L is an outcome measure, not a decision-quality measure.",
        )

        self.positions.save_post_trade_review(review)