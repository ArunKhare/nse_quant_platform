"""Paper decision loop: market data to post-trade review.


Flow:
market data -> analytics -> feature snapshot -> open-position monitoring
-> strategy proposal -> gates -> risk check -> paper order
-> independent leg positions -> marking/P&L -> exit evaluation
-> close -> post-trade review.
"""


from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from nse_quant.analytics.features import build_features
from nse_quant.core.models import (
    ChainSnapshot,
    LegPosition,
    MarketFeatures,
    OptionQuote,
    OrderSide,
    PaperOrder,
    PostTradeReview,
    StrategyPosition,
    StrategyPositionStatus,
    TradeProposal,
)
from nse_quant.core.settings import get_settings
from nse_quant.execution.broker import PaperBroker
from nse_quant.features.feature_store import FeatureStore
from nse_quant.ops.data_quality import DataQualityChecker, DataQualityReport
from nse_quant.ops.live_snapshot import build_snapshot, write_live_snapshot
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
        self.quality_checker = DataQualityChecker(
            stale_seconds=self.settings.runtime.stale_seconds,
        )

    def run_once(self) -> dict[str, Any]:
        snapshot = self.provider.get_chain_snapshot()
        persisted_rows = self.store.write_option_stream(
            self.run_id,
            snapshot,
        )
        features, iv_history_count = self._build_features(snapshot)
        quality: DataQualityReport = self.quality_checker.assess(snapshot)

        position_outcomes = self._monitor_open_positions(
            snapshot=snapshot,
            features=features,
            quality=quality,
        )

        self.feature_store.save(self.run_id, features)

        data_quality = {
            "is_usable": quality.is_usable,
            "stale": quality.stale,
            "missing_quotes": quality.missing_quotes,
            "missing_bid_ask": quality.missing_bid_ask,
            "zero_volume_legs": quality.zero_volume_legs,
            "issues": quality.issues,
            "warnings": quality.warnings,
        }

        self.decisions.save_decision(
            self.run_id,
            "data_quality",
            None,
            data_quality,
        )

        iv_smile = [
            {
                "strike": quote.instrument.strike,
                "option_type": quote.instrument.option_type.value,
                "iv": quote.iv,
            }
            for quote in snapshot.quotes
            if quote.iv is not None
        ]

        features.diagnostics["iv_smile"] = iv_smile

        iv_history = {
            "observation_count": iv_history_count,
            "minimum_required": (
                self.settings.analytics.min_iv_history_observations
            ),
            "mode": (
                "ENFORCED"
                if iv_history_count
                >= self.settings.analytics.min_iv_history_observations
                else "COLD_START"
            ),
        }

        open_positions = self.positions.get_open_strategy_positions()

        if len(open_positions) >= self.settings.risk.max_open_positions:
            return self._finish_cycle(
                status="max_open_positions",
                features=features,
                data_quality=data_quality,
                iv_history=iv_history,
                extra={
                    "open_positions": len(open_positions),
                    "position_outcomes": position_outcomes,
                    "persisted_option_rows": persisted_rows,
                },
            )

        proposal, gates = self.strategy.evaluate(
            snapshot,
            features,
            iv_history_count=iv_history_count,
        )

        if proposal:
            self.decisions.save_gate_results(
                self.run_id,
                proposal,
                gates,
            )

        if proposal is None:
            return self._finish_cycle(
                status="no_proposal",
                features=features,
                data_quality=data_quality,
                iv_history=iv_history,
                gates=gates,
                extra={
                    "position_outcomes": position_outcomes,
                    "persisted_option_rows": persisted_rows,
                },
            )

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
        risk_decision = self.risk.evaluate(
            proposal,
            features,
            quote_lookup,
        )

        self.decisions.save_risk_decision(
            self.run_id,
            proposal,
            risk_decision,
        )

        if not risk_decision.approved:
            return self._finish_cycle(
                status="risk_rejected",
                features=features,
                data_quality=data_quality,
                iv_history=iv_history,
                proposal=proposal,
                extra={
                    "proposal_id": proposal.proposal_id,
                    "reasons": risk_decision.reasons,
                    "position_outcomes": position_outcomes,
                    "persisted_option_rows": persisted_rows,
                },
            )

        if (
            self.settings.safety.dry_run
            or not self.settings.safety.trading_enabled
        ):
            self.decisions.save_decision(
                self.run_id,
                "dry_run_order_skipped",
                proposal,
                {"would_submit": True},
            )

            return self._finish_cycle(
                status="dry_run",
                features=features,
                data_quality=data_quality,
                iv_history=iv_history,
                proposal=proposal,
                extra={
                    "proposal_id": proposal.proposal_id,
                    "position_outcomes": position_outcomes,
                    "persisted_option_rows": persisted_rows,
                },
            )

        order = self.broker.submit(proposal)
        self._persist_order(order)

        if order.status.value != "FILLED":
            return self._finish_cycle(
                status=order.status.value,
                features=features,
                data_quality=data_quality,
                iv_history=iv_history,
                proposal=proposal,
                extra={
                    "proposal_id": proposal.proposal_id,
                    "reason": order.reject_reason,
                    "position_outcomes": position_outcomes,
                    "persisted_option_rows": persisted_rows,
                },
            )

        strategy_position, leg_positions = self._open_positions(
            proposal,
            order,
        )

        self._mark_positions(
            strategy_position=strategy_position,
            leg_positions=leg_positions,
            snapshot=snapshot,
        )

        exit_evaluation = self.exit_engine.evaluate(
            proposal,
            strategy_position,
            leg_positions,
            features,
            kill_switch_active=False,
            risk_breached=False,
            data_stale=not quality.is_usable,
        )

        self.positions.save_exit_evaluation(exit_evaluation)

        if exit_evaluation.selected_reason is not None:
            self._close_positions(
                proposal=proposal,
                strategy_position=strategy_position,
                leg_positions=leg_positions,
                exit_reason=exit_evaluation.selected_reason,
            )

        return self._finish_cycle(
            status="paper_filled",
            features=features,
            data_quality=data_quality,
            iv_history=iv_history,
            proposal=proposal,
            extra={
                "proposal_id": proposal.proposal_id,
                "strategy_position_id": strategy_position.strategy_position_id,
                "exit_reason": (
                    exit_evaluation.selected_reason.value
                    if exit_evaluation.selected_reason
                    else None
                ),
                "position_outcomes": position_outcomes,
                "persisted_option_rows": persisted_rows
            },
        )

    def _build_features(
        self,
        snapshot: ChainSnapshot,
    ) -> tuple[MarketFeatures, int]:
        iv_history = self.store.latest_iv_history(snapshot.underlying)
        spot_history = self.store.latest_spot_closes(
            instrument_token=256265,
            interval="minute",
            limit=60,
        )

        if not spot_history:
            spot_history = [snapshot.spot] * 30

        features = build_features(
            snapshot,
            iv_history,
            spot_history,
        )

        return features, len(iv_history)

    def _finish_cycle(
        self,
        status: str,
        features: MarketFeatures,
        data_quality: dict[str, Any],
        iv_history: dict[str, Any],
        proposal: TradeProposal | None = None,
        gates: list[Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.decisions.save_decision(
            self.run_id,
            status,
            proposal,
            {
                "gates": [
                    gate.model_dump(mode="json")
                    for gate in (gates or [])
                ],
                **(extra or {}),
            },
        )

        write_live_snapshot(
            build_snapshot(
                features=features,
                open_positions=self.positions.get_open_strategy_positions(),
                kill_switch_active=False,
                loop_status=status,
                data_quality=data_quality,
                iv_history=iv_history,
            )
        )

        return {
            "status": status,
            **(extra or {}),
            "gates": [
                gate.model_dump(mode="json")
                for gate in (gates or [])
            ],
        }

    @staticmethod
    def _quote_lookup(
        snapshot: ChainSnapshot,
    ) -> dict[tuple[str, float], OptionQuote]:
        return {
            (
                quote.instrument.option_type.value,
                quote.instrument.strike,
            ): quote
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
    ) -> tuple[StrategyPosition, list[LegPosition]]:
        filled_at = order.filled_at or datetime.now(UTC)
        entry_price = order.filled_price or proposal.entry_limit_price

        proposal_payload = proposal.model_dump(mode="json")

        metadata = {
            **proposal.metadata,
            "original_proposal": proposal_payload,
        }

        strategy_position = StrategyPosition(
            proposal_id=proposal.proposal_id,
            strategy=proposal.strategy,
            underlying=proposal.underlying,
            expiry=proposal.expiry,
            opened_at=filled_at,
            entry_price=entry_price,
            current_price=entry_price,
            thesis=proposal.thesis,
            metadata=metadata,
        )

        self.positions.create_strategy_position(strategy_position)

        leg_positions: list[LegPosition] = []

        for leg in proposal.legs:
            leg_position = LegPosition(
                leg_position_id=(
                    f"{strategy_position.strategy_position_id}:"
                    f"{leg.instrument.tradingsymbol}"
                ),
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
        strategy_position: StrategyPosition,
        leg_positions: list[LegPosition],
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
                mark = (
                    leg_position.current_price
                    or leg_position.entry_price
                )

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

    def handle_kill_switch(self) -> None:
        write_live_snapshot(
            build_snapshot(
                kill_switch_active=True,
                loop_status="kill_switch_active",
            )
        )

        self.decisions.save_system_event(
            run_id=self.run_id,
            event_type="kill_switch_active",
            payload={
                "reason": "dashboard_or_cli_kill_switch",
            },
        )

    def handle_loop_error(self, exc: Exception) -> dict[str, Any]:
        payload = {
            "error": str(exc),
            "error_type": type(exc).__name__,
        }

        self.decisions.save_system_event(
            run_id=self.run_id,
            event_type="loop_error",
            payload=payload,
        )

        return {
            "status": "loop_error",
            **payload,
        }

    @staticmethod
    def _mark_price(quote: OptionQuote | None) -> float | None:
        if quote is None:
            return None

        if (
            quote.bid is not None
            and quote.ask is not None
            and quote.ask >= quote.bid > 0
        ):
            return (quote.bid + quote.ask) / 2

        return quote.ltp

    def _close_positions(
        self,
        proposal: TradeProposal,
        strategy_position: StrategyPosition,
        leg_positions: list[LegPosition],
        exit_reason: Any,
    ) -> None:
        closed_at = datetime.now(UTC)

        strategy_position.status = StrategyPositionStatus.CLOSED
        strategy_position.closed_at = closed_at
        strategy_position.exit_reason = exit_reason
        strategy_position.realized_pnl = strategy_position.unrealized_pnl
        strategy_position.unrealized_pnl = 0.0

        self.positions.update_strategy_position(strategy_position)

        for leg_position in leg_positions:
            leg_position.status = StrategyPositionStatus.CLOSED
            leg_position.closed_at = closed_at
            leg_position.exit_reason = exit_reason
            leg_position.realized_pnl = leg_position.unrealized_pnl
            leg_position.unrealized_pnl = 0.0

            self.positions.update_leg_position(leg_position)

        review = PostTradeReview(
            strategy_position_id=strategy_position.strategy_position_id,
            proposal_id=proposal.proposal_id,
            strategy=proposal.strategy,
            closed_at=closed_at,
            realized_pnl=strategy_position.realized_pnl,
            exit_reason=exit_reason,
            thesis_status=(
                "VALID"
                if strategy_position.realized_pnl >= 0
                else "INVALID"
            ),
            decision_quality_notes=(
                "Thesis and gate evidence retained in decision history."
            ),
            outcome_notes=(
                "Realized P&L is an outcome measure, not a "
                "decision-quality measure."
            ),
        )

        self.positions.save_post_trade_review(review)

    def _monitor_open_positions(
        self,
        snapshot: ChainSnapshot,
        features: MarketFeatures,
        quality: DataQualityReport,
    ) -> list[dict[str, Any]]:
        outcomes: list[dict[str, Any]] = []

        for strategy_position in self.positions.get_open_strategy_positions():
            leg_positions = self.positions.get_leg_positions(
                strategy_position.strategy_position_id
            )

            if not leg_positions:
                continue

            self._mark_positions(
                strategy_position=strategy_position,
                leg_positions=leg_positions,
                snapshot=snapshot,
            )

            proposal = self._load_proposal(strategy_position)

            if proposal is None:
                outcomes.append(
                    {
                        "strategy_position_id": (
                            strategy_position.strategy_position_id
                        ),
                        "status": "missing_proposal",
                    }
                )
                continue

            exit_evaluation = self.exit_engine.evaluate(
                proposal,
                strategy_position,
                leg_positions,
                features,
                kill_switch_active=False,
                risk_breached=False,
                data_stale=not quality.is_usable,
            )

            self.positions.save_exit_evaluation(exit_evaluation)

            outcome = {
                "strategy_position_id": (
                    strategy_position.strategy_position_id
                ),
                "status": "open",
                "selected_exit_reason": (
                    exit_evaluation.selected_reason.value
                    if exit_evaluation.selected_reason
                    else None
                ),
            }

            if exit_evaluation.selected_reason is not None:
                self._close_positions(
                    proposal=proposal,
                    strategy_position=strategy_position,
                    leg_positions=leg_positions,
                    exit_reason=exit_evaluation.selected_reason,
                )

                outcome["status"] = "closed"

            outcomes.append(outcome)

        return outcomes

    def _load_proposal(
        self,
        strategy_position: StrategyPosition,
    ) -> TradeProposal | None:
        payload = strategy_position.metadata.get("original_proposal")

        if not payload:
            return None

        return TradeProposal.model_validate(payload)
