# Risk and safety

Defaults remain:

- `DRY_RUN=true`
- `TRADING_ENABLED=false`
- `PAPER_TRADING=true`

`RiskEngine` is independent from strategy logic. It checks allowed strategies,
lot limits, open-position limits, notional exposure, defined-risk structure,
and per-leg liquidity.

The exit priority is fixed:

`MANUAL_KILL_SWITCH -> RISK_LIMIT_BREACH -> EXPIRY_FORCE_CLOSE -> STOP_LOSS -> TARGET_PROFIT -> THETA_DECAY_TARGET -> IV_COLLAPSE -> EXPECTED_MOVE_VIOLATION -> DATA_QUALITY_EXIT`

All triggered exit reasons are persisted. Only the highest-priority reason is
used to close the strategy-position group.

Live order placement is structurally blocked by `KiteBroker`.