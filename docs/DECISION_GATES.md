# Pre-trade gates

The gate engine evaluates a `TradeProposal` against the latest `MarketFeatures` and returns a
`GateResult`. All gate outcomes are persisted.

| Gate | Purpose | Default rule |
|---|---|---|
| Market context | Avoid hostile regime | Reject strong trending regime for range strategies |
| Price structure | Avoid breakout against range thesis | Spot must remain inside the selected range |
| Liquidity | Ensure executable pricing | Minimum OI/volume and maximum spread percentage |
| Options positioning | Avoid extreme one-sided positioning | PCR within configured bounds |
| Volatility pricing | Prefer IV-rich conditions | IV rank and IV-RV spread minimums |
| Momentum confirmation | Avoid immediate adverse movement | Absolute short-term return below threshold |
| Execution quality | Avoid poor quote quality | Fresh quotes and acceptable spread |
| Risk approval | Enforce portfolio limits | Separate `RiskEngine` approval |
| Timing/psychology | Avoid unsuitable session periods | No first/last minutes; event blackout |

A proposal must pass every enabled gate. Gate failures are informational and persisted; they are
not strategy failures.
