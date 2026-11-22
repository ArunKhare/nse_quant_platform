# NSE Quant Platform — Implementation Charter

**Status:** Authoritative implementation contract  
**Version:** 1.0.0  
**Created:** 2026-11-22  
**Owner:** Platform owner  

This charter is the single source of truth for implementation decisions. It prevents architectural, regime, data, execution, and UI drift.

Any code, configuration, schema, strategy, or infrastructure change must either comply with this charter or explicitly propose a versioned charter amendment.

## 1. Purpose

Build a modular, auditable NSE quantitative decision platform that supports:

- Live market-data capture.
- Operational decision-making.
- Paper trading.
- Research and backtesting.
- Governed Medallion data pipelines.
- Versioned regime, feature, policy, and strategy artifacts.
- Future expansion to cash stocks, stock options, spreads, and multi-leg strategies.

The platform must remain safe, observable, reproducible, and portable between Windows 11 today and Linux/cloud deployment later.

## 2. Authoritative sources

The following sources govern implementation:

| Area | Authoritative source |
|---|---|
| Canonical options regime taxonomy and strategy playbook | `INFO/108-regime-strategy-playbook-v2.md` |
| Legacy regime reference | `INFO/108-regime-strategy-playbook.md` |
| Implementation decisions and constraints | `INFO/Drift-free implementation-Part1` through `Part4` |
| Quantitative governance principles | `INFO/framework-foundations-quantitative-measurement.md` |
| Optimization and governance principles | `INFO/quantitative-optimization-governance-operating-principles.md` |
| Strategy structures and controls | `INFO/strategy-structures-execution-risks-controls.md` |
| Current platform configuration | `config/settings.yaml` |
| Test configuration | `config/settings.test.yaml` |

INFO documents may contain informational guidance, external research, or proposed performance targets. Such content must be validated before it becomes a binding implementation requirement.

## 3. Locked platform decisions

| Decision | Locked value |
|---|---|
| Trading mode | Paper trading only |
| Live trading | Disabled until explicit authorization |
| Primary tradable underlying | NIFTY |
| Initial strategy | `iron_condor_monitor` |
| Decision-loop interval | 15 seconds |
| Option-chain capture interval | 30 seconds |
| Cash stocks | Research/context only initially; fully tradeable later |
| Stock options | Disabled |
| Index options beyond NIFTY | Disabled |
| Spreads | Disabled |
| Multi-leg strategies | Disabled |
| Alerts | Telegram |
| Dashboard | High priority |
| Deployment | Single user, multiple terminal processes |
| Current OS | Windows 11 |
| Future OS | Linux / cloud-ready |

## 4. Canonical architecture

The platform has two coordinated paths:

```text
Operational path
Kite capture → DuckDB → features/evidence → decision loop → paper orders

Medallion path
Capture → Bronze → Silver → Gold → versioned regime/policy artifacts

Live decision path
Fresh operational data + latest published Gold artifact → decision → audit/replay
```

The operational path must remain independent of heavy research, backtest, dashboard, and Medallion batch work.

The live decision loop must never synchronously wait for Bronze ingestion, Silver transformation, or Gold rebuilding.

## 5. Process ownership

The platform supports multiple terminal processes. Each mutable store has exactly one designated writer.

```text
kite_stream
├── Owns: market_data.duckdb
├── Writes: spot candles, option stream, chain snapshots
├── Refreshes: latest spot features
└── Publishes: latest market-state artifact

paper_loop
├── Owns: decisions.duckdb
├── Owns: paper_orders.duckdb
├── Reads: market_data.duckdb read-only
└── Writes: decisions, paper orders, audit events

dashboard
├── Reads: operational stores read-only
├── Reads: Silver/Gold Parquet read-only
└── Never writes directly to operational stores

tests
├── Use isolated temporary databases
├── Use mocked providers
└── Never touch live operational stores

research / backtest
├── Reads Silver/Gold Parquet read-only
└── Never writes operational stores
```

### Required store separation

```text
data/operational/market_data.duckdb
data/operational/decisions.duckdb
data/operational/paper_orders.duckdb
```

`kite_stream` and `paper_loop` must be able to run simultaneously in separate terminals without blocking one another.

The paper loop must not capture market data while `kite_stream` is active. Market capture and feature refresh belong to the capture/stream path; decision evaluation belongs to the paper loop.

### DuckDB rules

- One DuckDB connection per process.
- One writer per DuckDB database.
- Readers open databases in `read_only=True` mode.
- Never share a DuckDB connection across process boundaries.
- Never open a database read/write while another process owns it for writing.
- Close connections promptly after write transactions.
- Do not assume WAL solves cross-process writer contention.
- Use immutable Parquet for analytical access where appropriate.

DuckDB Quack server-based access is optional. It must be validated on Windows and Linux before adoption. It may later be introduced as a storage adapter if concurrent analytical access becomes necessary.

## 6. Regime contract

The canonical options regime taxonomy is defined by:

```text
INFO/108-regime-strategy-playbook-v2.md
```

The canonical regime has four components:

```text
IV state × term structure × skew × price action
```

The platform must use the exact four-component regime-label grammar and spelling from the v2 playbook.

### Binding rules

- Iron-condor eligibility uses the full institutional `regime_label`.
- Daily spot regimes such as `BULL|NORMAL` are market context only.
- `BULLISH`, `BEARISH`, and `MIXED` are multi-timeframe trend evidence, not regimes.
- Realized volatility is a separate risk/filter input, not a regime axis.
- The iron-condor allowlist contains only complete four-component regime labels.
- No strategy may compare incompatible regime vocabularies.
- Every regime artifact includes `regime_version`, `as_of`, `classifier_version`, and input provenance.
- Regime labels must be validated against the canonical registry.

The initial iron-condor eligibility set must include only the exact full four-component `HIGH_VOL_CHOP` regime labels identified in the v2 playbook.

## 7. Evidence-plugin contract

Every evidence plugin must declare one runtime mode:

```yaml
mode: observation      # evidence only
mode: risk_sizing      # can adjust size, stops, or risk limits
mode: hard_gate        # can block new entries
```

Initial default:

```text
All optional evidence plugins: observation
```

Promotion to `risk_sizing` or `hard_gate` requires:

- Explicit configuration change.
- Recorded rationale.
- Sufficient historical or paper validation.
- Operator approval where applicable.
- Audit logging of decision-time evidence and overrides.

Manual inference at execution or runtime is allowed, but every override must record:

```text
run_id
timestamp
plugin
mode
override_reason
evidence_used
decision_outcome
```

No plugin may silently replace an instrument-specific regime.

## 8. Cross-asset context

NIFTY options and cash stocks are distinct decision contexts.

```text
IndexOptionsContext
├── NIFTY option chain
├── IV surface / institutional regime
└── iron_condor_monitor

CashStockContext
├── equity candles and volume
├── stock-specific features
├── sector and market context
└── future cash-stock strategies
```

### Cash-stock scope

Cash stocks are research/context-only initially and may become fully tradeable later.

Initial cash-stock data:

- Daily candles.
- 1-minute candles.
- Derived intervals computed from 1-minute data as required.

Future cash-stock strategies:

- Swing and pullback trading.
- Breakout and momentum trading.
- Opening range breakout / gap-and-go.
- VWAP and moving-average pullbacks.
- Range and reversal trading.

### Breadth universe

The initial market-breadth universe is:

```text
NIFTY 200
```

The 10-stock cash watchlist is an execution/context watchlist, not the market-breadth universe.

Breadth must support:

- Advance/decline count and ratio.
- Percentage of constituents above 20/50/200-day moving averages.
- Up-volume versus down-volume ratio.
- Sector-level breadth and rotation.
- NIFTY versus equal-weight divergence.

### NIFTY options regime for cash stocks

NIFTY options regime primarily acts as a cash-stock risk adjustment.

It becomes a hard gate only for defined tail-risk or event conditions. It must never replace stock-specific regime logic.

## 9. Candle policy

The canonical intraday candle interval is:

```text
1 minute
```

Higher intervals are derived from 1-minute candles:

```text
1m → 3m → 5m → 15m → 30m → 60m → 4h
```

Daily candles remain a separate canonical EOD series.

### Derivation rules

- Do not separately capture or store every derived interval by default.
- Derive intervals through one shared, versioned resampling function.
- Materialize a derived interval only when required by a production feature, a versioned Gold artifact, or demonstrated query-performance need.
- Every derived feature records source interval, derivation version, source data range, and point-in-time timestamp.
- Derived candles must be reproducible from 1-minute source data.

## 10. Medallion contract

```text
Bronze
├── Immutable raw captures
├── Source payload and dual timestamps
└── Append-only storage

Silver
├── Normalized, validated, point-in-time data
├── Features and shared context
└── Reproducible transformations

Gold
├── Versioned regime artifacts
├── Approved strategy policies
├── Published research artifacts
└── Decision-ready contracts
```

Bronze is for live/raw capture. Silver is for near-real-time normalization and features. Gold is for stable, versioned decision and research artifacts.

The live decision loop reads:

```text
fresh operational DuckDB data
+ latest published Gold artifact
```

It does not query Bronze/Silver on the hot path.

### Artifact requirements

Every Gold artifact must include:

```text
artifact_name
artifact_version
published_at
source_time
source_data_range
input_provenance
classifier_version
policy_version
checksum or content hash
```

A stale, incomplete, or unavailable Gold artifact must block new entries according to the configured freshness policy.

## 11. Linux and cloud readiness

The platform must run on Windows 11 today and migrate cleanly to Linux or a cloud machine later.

Required rules:

- Use `pathlib.Path` and configuration-driven roots.
- Never hard-code `C:\` or `/srv/`.
- Use `TRADING_DATA_ROOT` for all data locations.
- Use cross-platform atomic writes: same-volume temporary file, close handle, then `os.replace()`.
- Avoid POSIX-only paths such as `/dev/shm` in application code.
- Make Redis optional and configurable through `REDIS_URL`.
- Keep process boundaries explicit.
- Use UTC internally; convert to IST only at market-session boundaries and presentation.
- Ensure every long-running process can restart safely without corrupting data.

## 12. Dashboard contract

The dashboard is implemented in Plotly Dash and runs as an independent read-only process.

Dash is chosen because it keeps the platform Python-only and avoids a separate React/TypeScript frontend and API contract. It is not a latency optimization; it is a maintainability and integration choice.

### Dashboard rules

- Dashboard reads operational DuckDB stores read-only.
- Dashboard reads Silver/Gold Parquet read-only.
- Dashboard reads the latest published Gold artifacts.
- Dashboard must not directly mutate the paper-loop database or live decision state.
- Manual kill switch is allowed only through an explicit, audited control interface.
- Use dropdowns and toggles rather than free-text operational commands where possible.

### Refresh policy

| Panel | Refresh interval |
|---|---|
| Kill switch, freshness, spot, VIX | 1–2 seconds |
| Regime and option-chain metrics | 5–15 seconds |
| Candle/feature charts | 15–60 seconds |
| Audit/backtest/research | On demand |

Use `dcc.Interval` for lightweight live panels. Use background callbacks for expensive historical, backtest, or research queries.

## 13. Testing and rollout

Each stage has a minimum critical-path test set:

- Contract/schema tests.
- Regime-label validation tests.
- Data-integrity and point-in-time tests.
- Decision-gate tests.
- Paper-trading validation.
- Audit/replay tests for governance-critical changes.
- Multi-process ownership tests.

Paper trading is the primary acceptance mechanism. A stage may proceed only after its critical tests pass and its paper-trading validation is recorded.

Tests must use isolated temporary storage and mocked providers. They must not write to live operational or paper-trading databases.

## 14. Implementation stages

```text
Stage 0: Freeze contracts
Stage 1: Standardize regimes and stabilize NIFTY options
Stage 2: Medallion foundation
Stage 3: Shared market context
Stage 4: Cash-stock research context
Stage 5: Backtest and promotion
Stage 6: Live readiness
```

### Stage 0 — Freeze contracts

Deliverables:

- Canonical regime enums and exact 108-label grammar.
- Regime artifact schema.
- Feature schema and feature-version contract.
- Decision-record schema.
- Strategy eligibility contract.
- Configuration schema for evidence plugins and trading contexts.
- Compatibility tests for regime-label parsing and serialization.

### Stage 1 — Stabilize NIFTY options

Deliverables:

- Fix iron-condor eligibility to consume institutional `regime_label`.
- Remove `BULL|NORMAL` from iron-condor eligibility comparison.
- Preserve daily regime and multi-timeframe trend as separate evidence.
- Make every evidence plugin runtime-configurable.
- Add explicit plugin health/staleness status.
- Add paper-loop decision audit records.
- Add kill-switch and stale-data guardrails.

### Stage 2 — Medallion foundation

Deliverables:

- `TRADING_DATA_ROOT` configuration.
- Bronze append-only writer with atomic Parquet output.
- Bronze schemas for option snapshots, spot candles, instrument master, orders, and events.
- Silver normalized schemas for equity bars, option chains, features, and context.
- Gold artifact publisher with version, published timestamp, source timestamp, and manifest.
- Read-only analytical access for dashboard, research, and backtests.

### Stage 3 — Shared context

Deliverables:

- Extend market context beyond NIFTY/BANKNIFTY.
- Add sector-index context.
- Add cash-stock daily and 1-minute capture.
- Add NIFTY 200 breadth dataset.
- Compute advance/decline, percent above moving averages, and sector rotation.
- Add cross-asset evidence fields to both NIFTY-option and cash-stock decisions.

### Stage 4 — Cash-stock research

Deliverables:

- Cash-stock context runner.
- Daily and 1-minute candle ingestion.
- Stock feature calculation.
- Cash-stock regime/evidence model.
- Research-only signal generators.
- No execution authority initially.

### Stage 5 — Backtest and promotion

Deliverables:

- Point-in-time backtest harness.
- Slippage, spread, liquidity, and corporate-action adjustments.
- Regime-level performance reporting.
- Minimum-trade and drawdown gates before promotion.
- Gold publication/admission workflow.

### Stage 6 — Live readiness

Deliverables:

- Explicit live-trading authorization workflow.
- Broker reconciliation.
- Order-rate limiting.
- Kill-switch enforcement.
- Alerting and dashboard operational views.
- Final production runbook.

No live trading occurs until this stage is explicitly approved.

## 15. Prohibited drift

The following are prohibited without a charter amendment:

- Adding a new regime vocabulary.
- Using `BULL|NORMAL` for iron-condor eligibility.
- Treating multi-timeframe alignment as a regime.
- Adding realized volatility as a fifth regime axis.
- Allowing a cash-stock decision to consume an index-option regime as its own regime.
- Letting a live decision synchronously depend on Bronze/Silver/Gold processing.
- Enabling live trading without an explicit authorization stage.
- Changing regime, feature, policy, or strategy behavior without a version bump.
- Writing research conclusions into production decisions without versioned provenance.
- Allowing multiple processes to write to the same DuckDB database.
- Running tests against live operational or paper-trading databases.
- Allowing the dashboard to directly mutate operational decision state.

## 16. Informational, not binding

The following items are guidance or future research topics, not immediate requirements:

- Sub-150 ms tick-to-order latency.
- 50–500 decisions per second.
- Seven to ten years of 1-minute option history.
- 100–150 trades per regime bucket.
- Kafka, Redis Streams, Delta Lake, or Iceberg.
- Quack server-based multi-process access.
- External historical option-data vendors.
- CPU pinning.
- Global garbage-collection disabling.
- Specific Redis or JSON serialization performance claims.

These require validation against actual Kite behavior, infrastructure, cost, and observed data quality before becoming binding requirements.

## 17. Amendment process

Any change to this charter requires:

1. A clear problem statement.
2. The proposed change.
3. Evidence or validation results.
4. Impact on regime, data, execution, security, and operations.
5. A version bump.
6. An updated changelog entry.

No implementation may silently deviate from this charter.
