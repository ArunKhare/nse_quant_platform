# Architecture

## Native target architecture
Received artifacts -> immutable Bronze -> typed source-linked Silver -> versioned
Gold -> published bundles -> native decisions and exact replay.

Legacy option_stream is not Bronze. Unknown provenance/times stay unknown;
provider identifiers do not establish canonical identity. Current research
publication admission still rejects point-in-time decision use. Native refusal
@1 does not run strategy, portfolio risk or execution. The accepted native-input
candidate is not decision admission or decision-loop cutover.

See [CURRENT_NATIVE_STATUS.md](CURRENT_NATIVE_STATUS.md) for current evidence,
remaining gates and operational holds. The user intentionally removed scripts/qa.

## Historical legacy paper-loop architecture

The pipeline and boundaries below describe the existing legacy paper-loop path,
not completed native cutover. The v0.3.0 broker statement below is historical;
current pyproject.toml declares project version 0.4.0. No live trading is authorized.

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
