# Architecture

`Kite -> TickNormalizer -> ChainSnapshot -> Analytics -> Gates -> Strategy -> RiskEngine -> PaperBroker -> PositionTracker -> DuckDB`

All deployment tunables are centralized in `config/settings.yaml`; secrets remain in `.env`; immutable domain constants remain in `core/constants.py`. Strategies emit proposals only; risk independently approves or rejects; execution performs state transitions.
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