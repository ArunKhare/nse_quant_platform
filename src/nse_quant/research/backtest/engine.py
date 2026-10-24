from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from nse_quant.analytics.features import build_features
from nse_quant.strategy.iron_condor import IronCondorMonitor

from .config import BacktestConfig
from .data import HistoricalDataLoader
from .portfolio import BacktestPortfolio


@dataclass
class BacktestResult:
    decisions: list[dict] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)

    @property
    def proposal_count(self) -> int:
        return sum(1 for decision in self.decisions if decision["proposal"] is not None)


class BacktestEngine:
    def __init__(
        self,
        config: BacktestConfig,
        strategy: IronCondorMonitor | None = None,
    ) -> None:
        self.config = config
        self.loader = HistoricalDataLoader(config)
        self.strategy = strategy or IronCondorMonitor()
        self.portfolio = BacktestPortfolio(self.config.initial_capital)

    def run(self) -> BacktestResult:
        snapshots = self.loader.load_market_hour_snapshots()

        result = BacktestResult()
        equity = self.config.initial_capital

        iv_history: deque[float] = deque(maxlen=500)
        spot_history: deque[float] = deque(maxlen=60)

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

            if proposal is not None and not self.portfolio.open_positions:
                self.portfolio.open_position(
                    proposal=proposal,
                    snapshot=snapshot,
                    slippage_pct=self.config.slippage_pct,
                )

            self.portfolio.mark_to_market(snapshot, features)
            if self.portfolio.open_positions:
                open_trade = self.portfolio.open_positions[0]

                if open_trade.realized_pnl is not None and open_trade.realized_pnl >= 0:
                    self.portfolio.close_positions()

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
                    "proposal": proposal.model_dump(mode="json") if proposal else None,
                    "gates": [gate.model_dump(mode="json") for gate in gates],
                }
            )

            result.equity_curve.append(
                {
                    "ts": snapshot.ts,
                    "equity": equity,
                }
            )

            # Update rolling history only after evaluating the snapshot.
            if features.atm_iv is not None and features.atm_iv > 0:
                iv_history.append(features.atm_iv)

            spot_history.append(snapshot.spot)

        return result

    def save(self, result: BacktestResult) -> Path:
        output_dir = self.config.output_dir / self.config.run_id
        output_dir.mkdir(parents=True, exist_ok=True)

        decisions = []
        trades = []

        for decision in result.decisions:
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
                    "opened_at": trade.opened_at,
                    "closed_at": trade.closed_at,
                    "entry_credit": trade.entry_credit,
                    "exit_debit": trade.exit_debit,
                    "realized_pnl": trade.realized_pnl,
                    "exit_reason": (trade.exit_reason.value if trade.exit_reason else None),
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
            "initial_capital": self.config.initial_capital,
        }

        (output_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, default=str),
            encoding="utf-8",
        )

        return output_dir
