from __future__ import annotations

from collections import Counter, deque
from datetime import date, datetime
from pathlib import Path

from nse_quant.analytics.features import build_features
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

iv_history: deque[float] = deque(maxlen=500)
spot_history: deque[float] = deque(maxlen=60)


for snapshot in loader.load_market_hour_snapshots():
    features = build_features(
        snapshot,
        iv_history=iv_history,
        close_history=spot_history,
    )

    proposal, gates = engine.strategy.evaluate(
        snapshot,
        features,
        iv_history_count=len(iv_history),
    )

    for gate in gates:
        if not gate.passed:
            key = (gate.gate, gate.reason)
            failures[key] += 1
            examples.setdefault(key, snapshot.ts)

    if features.atm_iv and features.atm_iv > 0:
        iv_history.append(features.atm_iv)

    spot_history.append(snapshot.spot)

for (gate, reason), count in failures.most_common():
    print(f"{count:5d}  {gate:30s}  {reason:50s}  first={examples[(gate, reason)]}")
