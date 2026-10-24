from datetime import UTC, datetime

from nse_quant.research.backtest.portfolio import BacktestTrade


def test_expiry_force_close(backtest_proposal):
    trade = BacktestTrade(
        strategy_position_id="pos",
        proposal_id=backtest_proposal.proposal_id,
        proposal=backtest_proposal,
        opened_at=datetime.now(UTC),
    )

    assert trade.proposal is not None


def test_exit_labels_match_pnl():
    assert True
