from nse_quant.research.trade_outcomes import TradeOutcome, summarize_outcomes


def test_summary_computes_trade_metrics() -> None:
    outcomes = [
        TradeOutcome(
            proposal_id="p1",
            underlying="NIFTY",
            strategy="iron_condor_monitor",
            regime="RANGE|HIGH",
            opened_at=None,
            closed_at=None,
            realized_pnl=100.0,
        ),
        TradeOutcome(
            proposal_id="p2",
            underlying="NIFTY",
            strategy="iron_condor_monitor",
            regime="RANGE|HIGH",
            opened_at=None,
            closed_at=None,
            realized_pnl=-40.0,
        ),
    ]

    summary = summarize_outcomes(outcomes)

    assert summary["trades"] == 2
    assert summary["wins"] == 1
    assert summary["pnl"] == 60.0
    assert summary["win_rate"] == 0.5
    assert summary["avg_pnl"] == 30.0
    assert summary["profit_factor"] == 2.5


def test_empty_summary_is_safe() -> None:
    summary = summarize_outcomes([])

    assert summary["trades"] == 0
    assert summary["pnl"] == 0.0
    assert summary["win_rate"] == 0.0
    assert summary["profit_factor"] == 0.0
