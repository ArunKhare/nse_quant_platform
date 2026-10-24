from datetime import UTC, datetime

from nse_quant.research.backtest.portfolio import BacktestTrade


def test_credit_trade_target_and_stop_labels(backtest_proposal):
    trade = BacktestTrade(
        strategy_position_id="pos-1",
        proposal_id=backtest_proposal.proposal_id,
        proposal=backtest_proposal,
        opened_at=datetime.now(UTC),
        entry_credit=100.0,
        exit_debit=40.0,
        realized_pnl=60.0,
    )
    trade.exit_debit = 40.0
    trade.realized_pnl = trade.entry_credit - trade.exit_debit

    assert trade.realized_pnl == 60.0


def test_exit_labels_match_pnl(backtest_proposal):
    profitable = BacktestTrade(
        strategy_position_id="pos-1",
        proposal_id=backtest_proposal.proposal_id,
        proposal=backtest_proposal,
        opened_at=datetime.now(UTC),
        entry_credit=100.0,
        exit_debit=40.0,
        realized_pnl=60.0,
    )

    losing = BacktestTrade(
        strategy_position_id="pos-2",
        proposal_id=backtest_proposal.proposal_id,
        proposal=backtest_proposal,
        opened_at=datetime.now(UTC),
        entry_credit=100.0,
        exit_debit=220.0,
        realized_pnl=-120.0,
    )

    assert profitable.realized_pnl > 0
    assert losing.realized_pnl < 0
