from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from nse_quant.analytics.features import build_features
from nse_quant.core.models import (
    ChainSnapshot,
    ExitReason,
    GateResult,
    MarketFeatures,
    TradeProposal,
)
from nse_quant.core.settings import get_settings
from nse_quant.strategy.iron_condor import IronCondorMonitor

from .config import BacktestConfig
from .data import HistoricalDataLoader
from .portfolio import BacktestPortfolio

IST = ZoneInfo("Asia/Kolkata")

settings = get_settings("config/settings.test.yaml")

print(
    "settings:",
    f"min_iv_rank={settings.analytics.min_iv_rank}",
    f"max_spread_pct={settings.get_effective_risk_settings('iron_condor_monitor').max_spread_pct}",
)


@dataclass
class BacktestResult:
    decisions: list[dict] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)

    @property
    def proposal_count(self) -> int:
        return sum(1 for decision in self.decisions if decision["proposal"] is not None)


@dataclass
class PreparedReplayStep:
    snapshot: ChainSnapshot
    features: MarketFeatures
    proposal: TradeProposal | None
    gates: list[GateResult]


@dataclass(frozen=True)
class PreparedFeatureStep:
    snapshot: ChainSnapshot
    features: MarketFeatures
    iv_history_count: int


class BacktestEngine:
    def __init__(
        self,
        config: BacktestConfig,
        strategy: IronCondorMonitor | None = None,
    ) -> None:
        self.config = config
        self.loader = HistoricalDataLoader(config)
        self.strategy = strategy or IronCondorMonitor()
        self.portfolio = BacktestPortfolio(
            initial_capital=self.config.initial_capital,
            config=self.config,
        )

    def run(
        self,
        snapshots: list[ChainSnapshot] | None = None,
        prepared_steps: list[PreparedReplayStep] | None = None,
        prepared_features: list[PreparedFeatureStep] | None = None,
    ) -> BacktestResult:
        if prepared_features is not None:
            return self.run_prepared_features(prepared_features)

        if prepared_steps is None:
            if snapshots is None:
                snapshots = self.loader.load_market_hour_snapshots()

            prepared_steps = self.prepare_replay(snapshots)

        result = BacktestResult()

        for step in prepared_steps:
            snapshot = step.snapshot
            features = step.features
            proposal = step.proposal
            gates = step.gates

            result = self._process_replay_step(
                result=result,
                snapshot=snapshot,
                features=features,
                proposal=proposal,
                gates=gates,
            )

        if self.config.force_close_eod and self.portfolio.open_positions:
            final_snapshot = prepared_steps[-1].snapshot
            self.portfolio.force_close_eod(
                final_snapshot,
                exit_reason=ExitReason.EOD_FORCE_CLOSE,
            )

        return result

    def _process_replay_step(
        self,
        *,
        result: BacktestResult,
        snapshot: ChainSnapshot,
        features: MarketFeatures,
        proposal: TradeProposal | None,
        gates: list[GateResult],
    ) -> BacktestResult:

        entry_allowed = self.portfolio.can_enter(
            snapshot_ts=snapshot.ts,
            max_open_positions=self.config.max_open_positions,
            cooldown_minutes=self.config.entry_cooldown_minutes,
        )

        if proposal is not None and entry_allowed:
            self.portfolio.open_position(
                proposal=proposal,
                snapshot=snapshot,
                features=features,
                slippage_pct=self.config.slippage_pct,
            )

        self.portfolio.mark_to_market(snapshot, features)

        if self.portfolio.open_positions:
            trade = self.portfolio.open_positions[0]

            if snapshot.ts > trade.opened_at:
                exit_reason = self.portfolio.evaluate_exit(
                    trade=trade,
                    snapshot=snapshot,
                    features=features,
                )

                if exit_reason is not None:
                    self.portfolio.close_position(
                        trade=trade,
                        exit_reason=exit_reason,
                        closed_at=snapshot.ts,
                        exit_spot=snapshot.spot,
                    )

        if self.config.force_close_eod and self.portfolio.open_positions:
            local_time = snapshot.ts.astimezone(ZoneInfo(self.config.timezone)).time()

            if local_time >= time.fromisoformat(self.config.market_close):
                self.portfolio.force_close_eod(
                    snapshot,
                    exit_reason=ExitReason.EOD_FORCE_CLOSE,
                )

        result.decisions.append(
            {
                "ts": snapshot.ts,
                "spot": snapshot.spot,
                "quote_count": len(snapshot.quotes),
                "atm_iv": features.atm_iv,
                "iv_rank": features.iv_rank,
                "realized_vol": features.realized_vol,
                "iv_rv_spread": features.iv_rv_spread,
                "expected_move_points": features.expected_move_points,
                "regime": features.regime.value,
                "liquidity_score": features.liquidity_score,
                "proposal": (proposal.model_dump(mode="json") if proposal else None),
                "gates": [gate.model_dump(mode="json") for gate in gates],
            }
        )

        result.equity_curve.append(
            {
                "ts": snapshot.ts,
                "equity": self.portfolio.cash,
                "open_positions": len(self.portfolio.open_positions),
            }
        )

        return result

    def save(self, result: BacktestResult) -> Path:
        output_dir = self.config.output_dir / self.config.run_id
        output_dir.mkdir(parents=True, exist_ok=True)

        decisions = []
        trades = []

        for decision in result.decisions:
            failed_gates = [gate["gate"] for gate in decision["gates"] if not gate["passed"]]

            decisions.append(
                {
                    "ts": decision["ts"],
                    "spot": decision["spot"],
                    "quote_count": decision["quote_count"],
                    "has_proposal": decision["proposal"] is not None,
                    "proposal_id": (
                        decision["proposal"]["proposal_id"] if decision["proposal"] else None
                    ),
                    "gate_count": len(decision["gates"]),
                    "all_gates_passed": all(gate["passed"] for gate in decision["gates"]),
                    "failed_gates": ",".join(failed_gates),
                    "failed_gate_count": len(failed_gates),
                }
            )
        pd.DataFrame(decisions).to_csv(
            output_dir / "decisions.csv",
            index=False,
        )

        pd.DataFrame(result.equity_curve).to_csv(
            output_dir / "equity_curve.csv",
            index=False,
        )

        for trade in self.portfolio.closed_trades:
            trades.append(
                {
                    "strategy_position_id": trade.strategy_position_id,
                    "proposal_id": trade.proposal_id,
                    "opened_at": trade.opened_at.astimezone(IST),
                    "closed_at": trade.closed_at.astimezone(IST) if trade.closed_at else None,
                    "entry_credit": trade.entry_credit,
                    "exit_debit": trade.exit_debit,
                    "realized_pnl": trade.realized_pnl,
                    "exit_reason": (trade.exit_reason.value if trade.exit_reason else None),
                    "proposal_net_credit": (
                        trade.proposal.metadata.get("net_credit") if trade.proposal else None
                    ),
                    "proposal_target_price": (
                        trade.proposal.target_price if trade.proposal else None
                    ),
                    "proposal_stop_loss_price": (
                        trade.proposal.stop_loss_price if trade.proposal else None
                    ),
                }
            )

        pd.DataFrame(trades).to_csv(
            output_dir / "trades.csv",
            index=False,
        )
        summary = {
            "run_id": self.config.run_id,
            "underlying": self.config.underlying,
            "start_date": self.config.start_date.isoformat(),
            "end_date": self.config.end_date.isoformat(),
            "snapshot_count": len(result.decisions),
            "proposal_count": result.proposal_count,
            "open_position_count": len(self.portfolio.open_positions),
            "closed_trade_count": len(self.portfolio.closed_trades),
            "initial_capital": self.config.initial_capital,
        }

        (output_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, default=str),
            encoding="utf-8",
        )

        return output_dir

    def prepare_replay(
        self,
        snapshots: list[ChainSnapshot],
    ) -> list[PreparedReplayStep]:
        iv_history: deque[float] = deque(maxlen=500)
        spot_history: deque[float] = deque(maxlen=60)

        steps: list[PreparedReplayStep] = []

        for snapshot in snapshots:
            features = build_features(
                snapshot,
                iv_history=iv_history,
                close_history=spot_history,
            )

            proposal, gates = self.strategy.evaluate(
                snapshot,
                features,
                iv_history_count=len(iv_history),
            )

            steps.append(
                PreparedReplayStep(
                    snapshot=snapshot,
                    features=features,
                    proposal=proposal,
                    gates=gates,
                )
            )

            if features.atm_iv is not None and features.atm_iv > 0:
                iv_history.append(features.atm_iv)

            spot_history.append(snapshot.spot)

        return steps

    def run_prepared_features(
        self,
        prepared_features: list[PreparedFeatureStep],
    ) -> BacktestResult:
        result = BacktestResult()

        for step in prepared_features:
            proposal, gates = self.strategy.evaluate(
                step.snapshot,
                step.features,
                iv_history_count=step.iv_history_count,
            )

            result = self._process_replay_step(
                result=result,
                snapshot=step.snapshot,
                features=step.features,
                proposal=proposal,
                gates=gates,
            )

        if self.config.force_close_eod and self.portfolio.open_positions:
            final_snapshot = prepared_features[-1].snapshot
            self.portfolio.force_close_eod(
                final_snapshot,
                exit_reason=ExitReason.EOD_FORCE_CLOSE,
            )

        return result

    def prepare_features(
        self,
        snapshots: list[ChainSnapshot],
    ) -> list[PreparedFeatureStep]:
        """Precompute parameter-independent replay features.

        Rolling IV and spot histories require sequential processing, but the
        resulting steps can be reused by every parameter-grid experiment.
        """
        iv_history: deque[float] = deque(maxlen=500)
        spot_history: deque[float] = deque(maxlen=60)

        steps: list[PreparedFeatureStep] = []

        for snapshot in snapshots:
            features = build_features(
                snapshot,
                iv_history=iv_history,
                close_history=spot_history,
            )

            steps.append(
                PreparedFeatureStep(
                    snapshot=snapshot,
                    features=features,
                    iv_history_count=len(iv_history),
                )
            )

            if features.atm_iv is not None and features.atm_iv > 0:
                iv_history.append(features.atm_iv)

            spot_history.append(snapshot.spot)

        return steps
