# Architecture


`Kite -> TickNormalizer -> ChainSnapshot -> Analytics -> FeatureStore -> Strategy -> Gates -> RiskEngine -> PaperBroker -> LegPositions -> ExitEngine -> PostTradeReview -> DuckDB`

## Boundaries

- Strategies emit `TradeProposal` objects only.
- Gates decide whether a strategy may propose a trade.
- The independent `RiskEngine` decides whether a proposal may proceed.
- `PaperBroker` is the only executable broker in v0.3.0.
- `KiteBroker` raises `LiveTradingDisabledError` for every mutating operation.
- Every feature snapshot, signal, gate result, risk decision, order, position, exit evaluation, and review is persisted.
- Dash is the only active UI framework.

## Live feature-history boundary

The decision loop reads real persisted 1m spot closes using the same `1m` interval used by the candle writer.
It does not synthesize flat price history when live history is unavailable.

If there are insufficient closes, realized volatility and IV-RV spread remain `null`, and downstream gates
must treat those fields as unavailable rather than zero.
