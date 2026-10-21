import pandas as pd

from nse_quant.research.iron_condor_backtest import (
    IronCondorBacktester,
    IronCondorConfig,
)


def make_frame() -> pd.DataFrame:
    rows = []

    for minute in range(10):
        ts = pd.Timestamp(
            f"2026-10-21 09:{20 + minute:02d}:00",
            tz="Asia/Kolkata",
        ).tz_convert("UTC")

        for expiry in [
            "2026-10-27",
            "2026-11-03",
        ]:
            for option_type, strikes in [
                ("PE", [22300, 22400]),
                ("CE", [23150, 23250]),
            ]:
                for strike in strikes:
                    rows.append(
                        {
                            "ts": ts,
                            "underlying": "NIFTY",
                            "expiry": expiry,
                            "strike": strike,
                            "option_type": option_type,
                            "ltp": 40.0,
                            "spot": 22800.0,
                            "delta": (
                                -0.20
                                if option_type == "PE"
                                else 0.20
                            ),
                        }
                    )

    return pd.DataFrame(rows)


def test_backtester_produces_end_of_day_trade():
    config = IronCondorConfig(
        wing_width=100,
        slippage_per_leg=0.0,
        brokerage_per_lot=0.0,
    )

    backtester = IronCondorBacktester(
        frame=make_frame(),
        config=config,
    )

    trades = backtester.run()

    assert len(trades) == 1
    assert trades[0].exit_reason == "end_of_day"
    assert trades[0].pnl == 0.0