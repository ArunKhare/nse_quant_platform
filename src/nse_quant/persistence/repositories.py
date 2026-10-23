"""Typed repositories over DuckDB tables."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from nse_quant.core.models import (
    ExitEvaluation,
    ExitReason,
    GateResult,
    LegPosition,
    PostTradeReview,
    RiskDecision,
    StrategyPosition,
    TradeProposal,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _json(value: Any) -> str:
    return json.dumps(value, default=str)


class DecisionRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def save_decision(
        self,
        run_id: str,
        decision_type: str,
        proposal: TradeProposal | None,
        payload: dict[str, Any],
    ) -> str:
        decision_id = uuid4().hex
        self.conn.execute(
            """
            INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                decision_id,
                _utcnow(),
                run_id,
                decision_type,
                proposal.proposal_id if proposal else None,
                proposal.strategy if proposal else None,
                proposal.underlying if proposal else None,
                proposal.expiry if proposal else None,
                _json(payload),
            ],
        )
        return decision_id

    def save_gate_results(
        self,
        run_id: str,
        proposal: TradeProposal,
        gates: list[GateResult],
    ) -> None:
        rows = [
            (
                uuid4().hex,
                _utcnow(),
                run_id,
                proposal.proposal_id,
                proposal.strategy,
                gate.gate,
                gate.passed,
                gate.reason,
                _json(gate.details),
            )
            for gate in gates
        ]

        if rows:
            self.conn.executemany(
                """
                INSERT INTO gate_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def save_risk_decision(
        self,
        run_id: str,
        proposal: TradeProposal,
        decision: RiskDecision,
    ) -> str:
        risk_decision_id = uuid4().hex
        self.conn.execute(
            """
            INSERT INTO risk_decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                risk_decision_id,
                _utcnow(),
                run_id,
                proposal.proposal_id,
                proposal.strategy,
                decision.approved,
                _json(decision.reasons),
                _json([check.model_dump(mode="json") for check in decision.checks]),
            ],
        )
        return risk_decision_id

    def save_system_event(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
        proposal: TradeProposal | None = None,
    ) -> str:
        """Persist a platform-level event that is not tied to a proposal."""

        decision_id = uuid4().hex

        self.conn.execute(
            """
            INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                decision_id,
                datetime.now(UTC),
                run_id,
                event_type,
                proposal.proposal_id if proposal else None,
                proposal.strategy if proposal else None,
                proposal.underlying if proposal else None,
                proposal.expiry if proposal else None,
                _json(payload),
            ],
        )
        return decision_id


class PositionRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def create_strategy_position(self, position: StrategyPosition) -> None:
        self.conn.execute(
            """
            INSERT INTO strategy_positions VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                position.strategy_position_id,
                position.proposal_id,
                position.strategy,
                position.underlying,
                position.expiry,
                position.opened_at,
                position.entry_price,
                position.current_price,
                position.realized_pnl,
                position.unrealized_pnl,
                position.status.value,
                position.exit_reason.value if position.exit_reason else None,
                _json([reason.value for reason in position.all_triggered_exits]),
                position.closed_at,
                position.thesis,
                _json(position.metadata),
            ],
        )

    def create_leg_position(self, position: LegPosition) -> None:
        self.conn.execute(
            """
            INSERT INTO positions VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                position.leg_position_id,
                position.strategy_position_id,
                position.proposal_id,
                position.strategy,
                position.instrument.underlying,
                position.instrument.expiry,
                position.instrument.tradingsymbol,
                position.instrument.instrument_token,
                position.instrument.option_type.value,
                position.instrument.strike,
                position.side.value,
                position.lots,
                position.quantity,
                position.opened_at,
                position.entry_price,
                position.current_price,
                position.realized_pnl,
                position.unrealized_pnl,
                position.status.value,
                position.closed_at,
                position.exit_reason.value if position.exit_reason else None,
            ],
        )

    def get_open_strategy_positions(self) -> list[StrategyPosition]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM strategy_positions
            WHERE status = 'OPEN'
            """
        ).fetchall()

        return [self._strategy_position_from_row(row) for row in rows]

    def get_daily_realized_pnl(self) -> float:
        day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        row = self.conn.execute(
            """
            SELECT COALESCE(SUM(realized_pnl), 0)
            FROM strategy_positions
            WHERE status = 'CLOSED'
              AND closed_at >= ?
              AND closed_at < ?
            """,
            [day_start, day_end],
        ).fetchone()
        return float(row[0])

    def get_leg_positions(self, strategy_position_id: str) -> list[LegPosition]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM positions
            WHERE strategy_position_id = ?
            """,
            [strategy_position_id],
        ).fetchall()

        return [self._leg_position_from_row(row) for row in rows]

    def update_strategy_position(self, position: StrategyPosition) -> None:
        self.conn.execute(
            """
            UPDATE strategy_positions
            SET current_price = ?,
                realized_pnl = ?,
                unrealized_pnl = ?,
                status = ?,
                exit_reason = ?,
                all_triggered_exits = ?,
                closed_at = ?
            WHERE strategy_position_id = ?
            """,
            [
                position.current_price,
                position.realized_pnl,
                position.unrealized_pnl,
                position.status.value,
                position.exit_reason.value if position.exit_reason else None,
                _json([reason.value for reason in position.all_triggered_exits]),
                position.closed_at,
                position.strategy_position_id,
            ],
        )

    def update_leg_position(self, position: LegPosition) -> None:
        self.conn.execute(
            """
            UPDATE positions
            SET current_price = ?,
                realized_pnl = ?,
                unrealized_pnl = ?,
                status = ?,
                closed_at = ?,
                exit_reason = ?
            WHERE position_id = ?
            """,
            [
                position.current_price,
                position.realized_pnl,
                position.unrealized_pnl,
                position.status.value,
                position.closed_at,
                position.exit_reason.value if position.exit_reason else None,
                position.leg_position_id,
            ],
        )

    def save_exit_evaluation(self, evaluation: ExitEvaluation) -> None:
        self.conn.execute(
            """
            INSERT INTO exit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                uuid4().hex,
                evaluation.evaluated_at,
                evaluation.strategy_position_id,
                evaluation.details.get("proposal_id"),
                evaluation.details.get("strategy"),
                _json([reason.value for reason in evaluation.triggered_reasons]),
                evaluation.selected_reason.value if evaluation.selected_reason else None,
                _json(evaluation.details),
            ],
        )

    def save_post_trade_review(self, review: PostTradeReview) -> None:
        self.conn.execute(
            """
            INSERT INTO post_trade_reviews VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                review.review_id,
                _utcnow(),
                review.strategy_position_id,
                review.proposal_id,
                review.strategy,
                review.realized_pnl,
                review.exit_reason.value,
                review.thesis_status,
                review.decision_quality_notes,
                review.outcome_notes,
            ],
        )

    def _strategy_position_from_row(self, row: tuple[Any, ...]) -> StrategyPosition:
        return StrategyPosition(
            strategy_position_id=row[0],
            proposal_id=row[1],
            strategy=row[2],
            underlying=row[3],
            expiry=row[4],
            opened_at=row[5],
            entry_price=float(row[6]),
            current_price=float(row[7]) if row[7] is not None else None,
            realized_pnl=float(row[8]),
            unrealized_pnl=float(row[9]),
            status=row[10],
            exit_reason=ExitReason(row[11]) if row[11] else None,
            all_triggered_exits=[ExitReason(item) for item in json.loads(row[12])],
            closed_at=row[13],
            thesis=row[14] or "",
            metadata=json.loads(row[15]) if row[15] else {},
        )

    def _leg_position_from_row(self, row: tuple[Any, ...]) -> LegPosition:
        from nse_quant.core.models import Instrument, OptionType, OrderSide

        lots = int(row[11])
        quantity = int(row[12])
        instrument = Instrument(
            tradingsymbol=row[6],
            instrument_token=int(row[7]),
            underlying=row[4],
            expiry=row[5],
            strike=float(row[9]),
            option_type=OptionType(row[8]),
            lot_size=quantity // lots if lots else 1,
        )

        return LegPosition(
            leg_position_id=row[0],
            strategy_position_id=row[1],
            proposal_id=row[2],
            strategy=row[3],
            instrument=instrument,
            side=OrderSide(row[10]),
            lots=lots,
            opened_at=row[13],
            entry_price=float(row[14]),
            current_price=float(row[15]) if row[15] is not None else None,
            realized_pnl=float(row[16]),
            unrealized_pnl=float(row[17]),
            status=row[18],
            closed_at=row[19],
            exit_reason=ExitReason(row[20]) if row[20] else None,
        )
