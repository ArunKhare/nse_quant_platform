from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from nse_quant.core.models import MarketFeatures
from nse_quant.strategy.iron_condor import IronCondorMonitor

from .config import BacktestConfig
from .data import HistoricalDataLoader


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

    def run(self) -> BacktestResult:
        snapshots = self.loader.load_market_hour_snapshots()

        result = BacktestResult()
        equity = self.config.initial_capital

        for snapshot in snapshots:
            features = MarketFeatures(
                ts=snapshot.ts,
                underlying=snapshot.underlying,
                spot=snapshot.spot,
                expiry=snapshot.expiry,
            )

            proposal, gates = self.strategy.evaluate(
                snapshot,
                features,
                iv_history_count=0,
            )

            result.decisions.append(
                {
                    "ts": snapshot.ts,
                    "spot": snapshot.spot,
                    "quote_count": len(snapshot.quotes),
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

        return result

    def save(self, result: BacktestResult) -> Path:
        output_dir = self.config.output_dir / self.config.run_id
        output_dir.mkdir(parents=True, exist_ok=True)

        decisions = []

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
