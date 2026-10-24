from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from pathlib import Path

from nse_quant.core.models import MarketFeatures
from nse_quant.research.backtest.config import BacktestConfig
from nse_quant.research.backtest.data import HistoricalDataLoader
from nse_quant.research.backtest.engine import BacktestEngine

config = BacktestConfig(
    warehouse_dir=Path("data/exports"),
    output_dir=Path("data/research/backtests"),
    underlying="NIFTY",
    start_date=date(2026, 10, 21),
    end_date=date(2026, 10, 23),
)

loader = HistoricalDataLoader(config)
engine = BacktestEngine(config)

failures: Counter[tuple[str, str]] = Counter()
examples: dict[tuple[str, str], datetime] = {}

for snapshot in loader.load_market_hour_snapshots():
    features = MarketFeatures(
        ts=snapshot.ts,
        underlying=snapshot.underlying,
        spot=snapshot.spot,
        expiry=snapshot.expiry,
    )

    proposal, gates = engine.strategy.evaluate(
        snapshot,
        features,
        iv_history_count=0,
    )

    for gate in gates:
        if not gate.passed:
            key = (gate.gate, gate.reason)
            failures[key] += 1
            examples.setdefault(key, snapshot.ts)

for (gate, reason), count in failures.most_common():
    print(f"{count:5d}  {gate:30s}  {reason:50s}  first={examples[(gate, reason)]}")
