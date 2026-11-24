# NSE Quant Platform — Implementation Charter

**Status:** Authoritative implementation contract  
**Version:** 1.1.1  
**Created:** 2026-11-22  
**Last updated:** 2026-11-24  
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

| Area | Authoritative source |
|---|---|
| Canonical options regime taxonomy and strategy playbook | `INFO/108-regime-strategy-playbook-v2.md` |
| Legacy regime reference | `INFO/108-regime-strategy-playbook.md` |
| Implementation decisions and constraints | `INFO/Drift-free implementation-Part1` through `Part4` |
| Quantitative governance principles | `INFO/framework-foundations-quantitative-measurement.md` |
| Optimization and governance principles | `INFO/quantitative-optimization-governance-operating-principles.md` |
| Strategy structures and controls | `INFO/strategy-structures-execution-risks-controls.md` |
| Iron-condor operational manual | `docs/strategies/iron_condor_master_manual.md` |
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
├── Reads: published market-state snapshots or a validated read-only storage-service interface
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

- DuckDB connections and analytical sessions are process-local and explicitly owned; never inherit, serialize, or share them across processes.
- A process may own separate connections for distinct stores or roles when their ownership, access mode, lifecycle, independent transactions, and combined resource budget are explicit. This does not authorize competing processes to open the same mutable database file.
- Prefer one reusable connection per store/service role within a process; avoid per-query connection churn.
- One writer per DuckDB database.
- Direct-file readers use `read_only=True` only when compatible with file ownership. This flag does not permit an independent reader process to bypass another process's native read/write file lock.
- While a mutable database is held by its writer process, other processes consume immutable published snapshots/Parquet or a validated storage-service interface. They do not directly open that live file.
- A Quack service, when validated and enabled, is the sole direct owner of its database files. Client roles retain dataset-level write ownership; local client connection flags are not server-side authorization.
- Never share a DuckDB connection across process boundaries.
- Never open a database read/write while another process owns it for writing.
- Close connections promptly after write transactions.
- Do not assume WAL solves cross-process writer contention.
- Use immutable Parquet for analytical access where appropriate.

DuckDB Quack server-based access is optional. It must be validated on Windows and Linux before adoption. It may later be introduced as a storage adapter if concurrent analytical access becomes necessary.

### Multi-terminal validation boundary

The target remains a single-user platform with independent capture, paper-loop, dashboard, Medallion, and research processes. Connection-count wording must not force these roles into one process or make research block live capture/decisions.

Quack remains an optional, explicitly validated adapter, not an automatically activated dependency. Before operational cutover, tests must exercise concurrent writer progress, independent paper/dashboard/research clients, writer ownership, rejected unauthorized writes, failure/cleanup behavior, and bounded resource configuration on supported Windows and Linux environments. A synthetic capability probe is not validation of the actual application entry points.

Existing operational runners must be inspected and migrated explicitly. A store factory or installed extension alone is not evidence that an entry point uses it. Do not remove broker/risk controls or silently fall back to competing direct-file opens if a service is unavailable.

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
- Realized volatility is not a fifth regime axis.
- The iron-condor allowlist contains only complete four-component regime labels.
- No strategy may compare incompatible regime vocabularies.
- Every regime artifact includes `regime_version`, `as_of`, `classifier_version`, and input provenance.
- Regime labels must be validated against the canonical registry.

### Canonical price-action states

The canonical price-action states are:

```text
STRONG_BULL_TREND
STRONG_BEAR_TREND
RANGE_HIGH
RANGE_LOW
COMPRESSION
HIGH_VOL_CHOP
```

The current v4 price-action states must not be silently reinterpreted as canonical playbook states. A new versioned classifier must produce the canonical states.

## 7. Realized volatility contract

Realized volatility is not a fifth regime axis.

The canonical institutional regime remains:

```text
IV state × term structure × skew × price action
```

However, realized volatility is required for:

1. Price-action classification, especially distinguishing `COMPRESSION` from `HIGH_VOL_CHOP`.
2. Mandatory iron-condor entry validation through variance risk premium.
3. Optional risk-sizing inputs after validation.

### Variance risk premium

The iron-condor master manual requires positive variance risk premium before entry:

```text
VRP = IV² - E[RV²] > 0
```

Where:

- `IV` is current 30-day constant-maturity implied volatility.
- `E[RV²]` is a forecast of realized variance over the 30-day holding period.
- A positive VRP is required before an iron-condor entry can be considered.
- High IV Rank alone does not authorize an entry.

A regime label permits strategy evaluation; it does not authorize a trade until VRP and all other mandatory gates pass.

### Regime-label rule

Do not append RV, VRP, or trend to the regime label.

```text
Correct:
HIGH_IV_CONTANGO_NORMAL_SKEW_HIGH_VOL_CHOP

Incorrect:
HIGH_IV_CONTANGO_NORMAL_SKEW_HIGH_VOL_CHOP_POSITIVE_VRP
```

Every decision record must retain:

```text
regime label
classifier version
realized volatility input
VRP result
VRP gate outcome
```

## 8. Evidence-plugin contract

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

## 9. Multi-timeframe trend contract

Multi-timeframe trend is spot-price directional evidence.

It is not a regime axis and must not be appended to the canonical four-component institutional regime label.

The canonical regime remains:

```text
IV state × term structure × skew × price action
```

### Permitted roles

Multi-timeframe trend may:

- Provide observational context.
- Support the price-action classifier as a validated input.
- Act as a strategy-specific timing or risk-sizing filter after validation.
- Be displayed in the dashboard and retained in decision audit records.

### Prohibited roles

Multi-timeframe trend must not:

- Become a fifth regime axis.
- Automatically block iron-condor entries.
- Replace the canonical price-action classifier.
- Override the institutional regime label.

### Iron-condor timing filter

`iron_condor_monitor` has a dedicated, versioned multi-timeframe timing filter:

```text
multi_timeframe_timing_v1
```

Initial mode:

```yaml
timing_filter:
  enabled: true
  mode: observation
  min_trend_strength: 0.0005
  required_timeframes:
    - 15m
    - 60m
```

In observation mode, the filter:

- Records alignment and reasons.
- Never blocks an entry.
- Always returns `size_multiplier = 1.0`.

In `risk_sizing` mode, misalignment may reduce size.

In `hard_gate` mode, misalignment may block new entries.

Weak or unavailable trend context is treated as `OBSERVE`, not `BLOCK`, even in hard-gate mode.

The feature gate must not treat multi-timeframe misalignment as a blocking reason by default. The strategy-specific timing filter owns any future gating or sizing decision.

## 10. Cross-asset context

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

## 11. Candle policy

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

## 12. Medallion contract

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

## 13. Linux and cloud readiness

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

## 14. Dashboard contract

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

## 15. Testing and rollout

Each stage has a minimum critical-path test set:

- Contract/schema tests.
- Regime-label validation tests.
- Data-integrity and point-in-time tests.
- Decision-gate tests.
- Timing-filter tests.
- Paper-trading validation.
- Audit/replay tests for governance-critical changes.
- Multi-process ownership tests.

Paper trading is the primary acceptance mechanism. A stage may proceed only after its critical tests pass and its paper-trading validation is recorded.

Tests must use isolated temporary storage and mocked providers. They must not write to live operational or paper-trading databases.

## 16. Implementation stages

```text
Stage 0: Freeze contracts — COMPLETE
Stage 1: Standardize regimes and stabilize NIFTY options — IN PROGRESS
Stage 2: Medallion foundation
Stage 3: Shared market context
Stage 4: Cash-stock research context
Stage 5: Backtest and promotion
Stage 6: Live readiness
```

### Stage 0 — Freeze contracts

Status: complete.

Deliverables:

- Implementation charter.
- Evidence-plugin runtime modes.
- Operational store paths and factory.
- Store-ownership tests.
- Dependency updates.
- Iron-condor master manual.
- Configuration repair.

### Stage 1 — Standardize regimes and stabilize NIFTY options

Status: in progress.

Deliverables:

- Canonical regime registry.
- Playbook-aligned institutional regime classifier.
- Exact iron-condor regime-label allowlist.
- Realized-volatility/VRP validation contract.
- Strategy-specific multi-timeframe timing filter.
- Removal of implicit multi-timeframe hard gate.
- Paper-loop audit fields for regime, VRP, timing filter, and evidence provenance.
- Stale-data and kill-switch guardrails.

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

## 17. Prohibited drift

The following are prohibited without a charter amendment:

- Adding a new regime vocabulary.
- Using `BULL|NORMAL` for iron-condor eligibility.
- Treating multi-timeframe trend as a regime.
- Adding realized volatility as a fifth regime axis.
- Appending RV, VRP, or trend to a regime label.
- Allowing a cash-stock decision to consume an index-option regime as its own regime.
- Letting a live decision synchronously depend on Bronze/Silver/Gold processing.
- Enabling live trading without an explicit authorization stage.
- Changing regime, feature, policy, or strategy behavior without a version bump.
- Writing research conclusions into production decisions without versioned provenance.
- Allowing multiple processes to write to the same DuckDB database.
- Running tests against live operational or paper-trading databases.
- Allowing the dashboard to directly mutate operational decision state.
- Treating multi-timeframe misalignment as an implicit feature-gate rejection.

## 18. Informational, not binding

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

## 19. Amendment process

Any change to this charter requires:

1. A clear problem statement.
2. The proposed change.
3. Evidence or validation results.
4. Impact on regime, data, execution, security, and operations.
5. A version bump.
6. An updated changelog entry.

No implementation may silently deviate from this charter.

## 20. Changelog

### 1.1.1 — 2026-11-24

- Clarified process-local ownership rather than a global one-connection-per-process cap.
- Preserved single-user, multi-terminal execution and explicit dataset writer ownership.
- Clarified native DuckDB file locks versus immutable snapshots and validated Quack access.
- Required server-side authorization and actual runner/concurrency validation before service cutover.
- No change to paper-only permissions, strategy/regime authority, or Quack's validation requirement.

### 1.1.0 — 2026-11-22

- Clarified realized-volatility contract.
- Added mandatory VRP entry-validation requirement for iron condors.
- Clarified that RV supports price-action classification but is not a regime axis.
- Clarified multi-timeframe trend as strategy-specific evidence.
- Added versioned `multi_timeframe_timing_v1` iron-condor timing filter.
- Made multi-timeframe trend observation-only by default.
- Removed implicit multi-timeframe feature-gate rejection as the default behavior.
- Added canonical price-action states.
- Marked Stage 0 complete and Stage 1 in progress.

### 1.0.0 — 2026-11-22

- Initial charter.
- Locked paper-only safety, NIFTY-only scope, regime contract, evidence governance, store ownership, Medallion architecture, candle policy, dashboard choice, and implementation stages.
