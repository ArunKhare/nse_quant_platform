"""Fixed-priority exit evaluation for strategy positions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from nse_quant.core.models import (
    EXIT_PRIORITY,
    ExitEvaluation,
    ExitReason,
    LegPosition,
    MarketFeatures,
    StrategyPosition,
    TradeProposal,
)
from nse_quant.core.settings import get_settings


class ExitEngine:
    def __init__(self, settings: Any | None = None) -> None:
        if settings is None:
            settings = get_settings()

        if hasattr(settings, "theta_decay_target_pct"):
            # A resolved ExitSettings object was supplied.
            self.settings = settings
            self.exit_settings = settings
        else:
            # Full Settings object was supplied.
            self.settings = settings
            self.exit_settings = settings.exits

    def evaluate(
        self,
        proposal: TradeProposal,
        strategy_position: StrategyPosition,
        leg_positions: list[LegPosition],
        features: MarketFeatures,
        kill_switch_active: bool = False,
        risk_breached: bool = False,
        data_stale: bool = False,
    ) -> ExitEvaluation:
        triggered: list[ExitReason] = []
        details: dict[str, Any] = {
            "proposal_id": proposal.proposal_id,
            "strategy": proposal.strategy,
            "current_price": strategy_position.current_price,
        }

        if kill_switch_active:
            triggered.append(ExitReason.MANUAL_KILL_SWITCH)

        if risk_breached:
            triggered.append(ExitReason.RISK_LIMIT_BREACH)

        if features.expiry <= features.ts.date():
            triggered.append(ExitReason.EXPIRY_FORCE_CLOSE)

        current_price = strategy_position.current_price

        if current_price is not None:
            if proposal.stop_loss_price is not None and current_price >= proposal.stop_loss_price:
                triggered.append(ExitReason.STOP_LOSS)

            if proposal.target_price is not None and current_price <= proposal.target_price:
                triggered.append(ExitReason.TARGET_PROFIT)

        exit_settings = self.exit_settings
        entry_price = strategy_position.entry_price

        if entry_price > 0 and current_price is not None:
            decay_pct = ((entry_price - current_price) / entry_price) * 100
            details["premium_decay_pct"] = decay_pct

            if decay_pct >= exit_settings.theta_decay_target_pct:
                triggered.append(ExitReason.THETA_DECAY_TARGET)

        if (
            features.atm_iv is not None
            and features.iv_rank is not None
            and features.iv_rank < exit_settings.iv_collapse_pct
        ):
            triggered.append(ExitReason.IV_COLLAPSE)

        if (
            features.expected_move_points is not None
            and proposal.expected_move_points is not None
            and features.expected_move_points
            > proposal.expected_move_points * exit_settings.expected_move_violation_buffer
        ):
            triggered.append(ExitReason.EXPECTED_MOVE_VIOLATION)

        if data_stale:
            triggered.append(ExitReason.DATA_QUALITY_EXIT)

        selected = self._select_highest_priority(triggered)

        return ExitEvaluation(
            strategy_position_id=strategy_position.strategy_position_id,
            evaluated_at=datetime.now(UTC),
            triggered_reasons=triggered,
            selected_reason=selected,
            details=details,
        )

    @staticmethod
    def _select_highest_priority(triggered: list[ExitReason]) -> ExitReason | None:
        if not triggered:
            return None

        triggered_set = set(triggered)

        for reason in EXIT_PRIORITY:
            if reason in triggered_set:
                return reason

        return None
