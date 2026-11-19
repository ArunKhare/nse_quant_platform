"""Connect walk-forward experiments to deterministic vectorbt evaluation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nse_quant.research.backtest.vectorbt_backtest import (
    VectorbtBacktestRequest,
    run_vectorbt_backtest,
)


def evaluate_vectorbt_fold(
    *,
    request_factory: Callable[[Any], VectorbtBacktestRequest],
    fold: Any,
) -> dict[str, Any]:
    """Evaluate one walk-forward fold using vectorbt."""
    request = request_factory(fold)
    result = run_vectorbt_backtest(request)

    return {
        "fold_id": fold.fold_id,
        "available": result["available"],
        "trades": result["trade_count"],
        "pnl": result["total_return"],
        "wins": result["win_rate"],
        "equity_curve": result["equity_curve"],
        "decision_eligibility_asserted": False,
    }
