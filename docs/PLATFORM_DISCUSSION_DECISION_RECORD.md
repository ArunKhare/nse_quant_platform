# Platform Architecture and Implementation Discussion Record

Status: discussion record, not an authorization to release held work, enable live trading, or close native gates.

## 1. Purpose

This document records the architecture and implementation discussion for the NSE Quant Decision Platform, including the relationship between the legacy paper loop, the Medallion architecture, the native governance increments, configuration, analytics/research overlap, dashboard scope, and remaining operational holds.

## 2. Executive summary

The platform has two related but distinct paths:

1. The legacy paper decision loop, which is the currently operational application path.
2. The native Medallion path, which is the target data, evidence, governance, and replay architecture.

The recent P0-P5 governance work strengthens the native Medallion path. It does not replace the legacy paper loop, does not close all native gates, and does not authorize production cutover or live trading.

## 3. Architecture

### 3.1 Native Medallion path

The native target architecture is:

```text
Received artifacts
  -> immutable Bronze
  -> typed source-linked Silver
  -> versioned Gold
  -> published bundles
  -> native decisions
  -> exact replay
```

This is the Medallion architecture described in `docs/CURRENT_NATIVE_STATUS.md` and `docs/ARCHITECTURE.md`.

### 3.2 Legacy paper loop

The legacy paper-loop architecture is:

```text
Kite
  -> TickNormalizer
  -> ChainSnapshot
  -> Analytics
  -> FeatureStore
  -> Strategy
  -> Gates
  -> RiskEngine
  -> PaperBroker
  -> LegPositions
  -> ExitEngine
  -> PostTradeReview
  -> DuckDB
```

This remains the currently running application path for the NIFTY paper decision loop and Dash UI.

### 3.3 Relationship

The Medallion architecture is the foundation. The recent P0-P5 work is the governance layer built on top of it.

They are not separate systems:

- `data_platform` is the Medallion and governance core.
- The other `src/nse_quant` folders provide the application runtime.
- The legacy paper loop remains the currently running application path.
- The native Medallion path is the target architecture.

## 4. Source package responsibilities

| Folder | Current relevance | Responsibility |
|---|---|---|
| `src/nse_quant/core` | Active | Typed settings, configuration precedence, secrets, shared models |
| `src/nse_quant/market_data` | Active | Market-data symbols, intervals, Kite integration inputs |
| `src/nse_quant/analytics` | Active | Live IV, RV, regime, features, greeks, decision analytics |
| `src/nse_quant/strategy` | Active | Strategy profiles and proposal-producing strategy logic |
| `src/nse_quant/risk` | Active | Portfolio and strategy risk controls |
| `src/nse_quant/execution` | Active but constrained | Paper broker and non-executing Kite boundary |
| `src/nse_quant/persistence` | Active | DuckDB persistence for decisions, positions, evidence, policies |
| `src/nse_quant/ops` | Active | Kill switch, live snapshot, operational state |
| `src/nse_quant/ui` | Active | Dash operations console |
| `src/nse_quant/research` | Active | Research-only evaluators, backtesting, research reports |
| `src/nse_quant/data_platform` | Active and central | Medallion Bronze/Silver/Gold, publication, admission, governance, lifecycle, execution governance, expansion |

## 5. P0-P5 implementation status

### 5.1 P0 - Native evidence completeness

P0 is complete in the updated `docs/CURRENT_NATIVE_STATUS.md`.

The implemented chain includes:

- Authoritative identity, derivative binding, and authorized revocation evidence.
- Availability and economic-validity evidence.
- Acceptance and reconciliation.
- Decision-loop linkage.
- Real accepted-authority integration.
- Completeness-report integration.
- Completeness-report audit-trail integration.
- Final-audit integration.
- End-to-end validation.
- Platform acceptance verification.
- Release readiness verification.
- Production cutover readiness.
- Operational cutover authorization.
- Production cutover execution authorization.
- Execution readiness.
- Execution completion.

### 5.2 P1 - Gold/admission chain

P1 is complete.

The implemented chain includes:

- Gold publication-candidate validation.
- Eligible admission-contract evaluation.
- Immutable admission envelope.
- Admission fingerprint.
- Exact replay.
- Final P1 acceptance.

### 5.3 P2 - Lifecycle/recovery

P2 is complete.

The implemented chain includes:

- Audit-trail lifecycle/replay.
- Recovery beyond bounded first-write profiles.
- Immutable recovery envelope.
- Recovery fingerprint.
- Exact replay.
- Final P2 acceptance.

### 5.4 P3 - Operational acceptance

P3 is complete.

The implemented chain includes:

- Existing operational acceptance harness.
- Multi-day integrated acceptance.
- Immutable acceptance envelope.
- Acceptance fingerprint.
- Exact replay.
- Final P3 acceptance.

### 5.5 P4 - Controlled execution

P4 is complete.

The implemented chain includes:

- Existing controlled execution gateway.
- Kite order placement integration.
- Reconciliation.
- Margin.
- Partial fills.
- Rule-based exits.
- Immutable execution envelope.
- Execution fingerprint.
- Exact replay.
- Final P4 acceptance.

### 5.6 P5 - Expansion

P5 is complete.

The implemented chain includes:

- Existing multi-underlying expansion validation.
- Stock options.
- Stocks.
- Spreads.
- Multi-leg strategies.
- Immutable completion envelope.
- Expansion fingerprint.
- Exact replay.
- Final P5 acceptance.

## 6. Important distinction

Completing P0-P5 coding does not mean the platform is production-cutover authorized.

The native status document still lists seven remaining gates:

1. Independently authenticated governance/namespace authority and real lifecycle evidence.
2. Authoritative underlying identity, derivative binding and authorized revocation.
3. Independently evidenced availability and economic validity.
4. A new sufficient eligible publication/admission contract.
5. Research lifecycle/recovery beyond bounded first-write profiles.
6. Complete required native strategy/analytics inputs, actual audited native strategy/risk decisions and complete exact replay.
7. Full integrated and operational acceptance.

Package QA is not platform acceptance.

## 7. Configuration architecture

### 7.1 Current state

The current configuration is valid for the legacy paper loop and evidence plugins, but it is not yet a complete Medallion configuration.

`config/settings.yaml` and `src/nse_quant/core/settings.py` configure:

- Safety.
- Universe.
- Runtime.
- Storage.
- Analytics.
- Risk.
- Exits.
- Paper execution.
- Market data.
- Notifier.
- Research.
- Strategies.
- Evidence plugins.
- Debug.

They do not yet expose a dedicated top-level Medallion section for Bronze, Silver, Gold, publication, admission, governance, native execution, or expansion.

### 7.2 Where Medallion contracts live

Medallion contracts live primarily in `src/nse_quant/data_platform/contracts.py` and in the individual Bronze/Silver/Gold modules.

The central contract model is:

```python
class Layer(StrEnum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
```

```python
class WritePolicy(StrEnum):
    APPEND_OBSERVATIONS = "append_observations"
    APPEND_REVISIONS = "append_revisions"
    VERSIONED_BUILDS = "versioned_builds"
```

```python
@dataclass(frozen=True)
class DatasetContract:
    name: str
    version: str
    layer: Layer
    write_policy: WritePolicy
    entity_keys: tuple[str, ...]
    required_columns: tuple[str, ...]
    owner: str
```

Contracts enforce:

- Bronze uses append observations.
- Silver uses append revisions.
- Gold uses versioned builds.
- Bronze requires received_at, source, and payload_hash.
- Silver requires recorded_at, source_observation_id, and revision_id.
- Gold requires build_id, event_ts, published_at, and feature_version.

### 7.3 Where Medallion settings live

Medallion settings currently live mostly inside individual data-platform modules as module-local constants, versions, commands, contracts, domains, and tables.

They are not centralized in `config/settings.yaml` or `src/nse_quant/core/settings.py`.

### 7.4 Recommended hybrid design

The recommended design is:

```text
Central settings:
  operational choices only

Module-local contracts:
  schema, version, write policy, validation, replay, safety
```

This means:

- Keep `DatasetContract`, schema, write policy, validation, and replay rules module-local.
- Centralize only safe operational settings such as paths, enablement, retention, execution mode, and expansion underlyings.
- Do not allow YAML to weaken contracts or safety boundaries.

### 7.5 Proposed Medallion settings

A proposed `medallion` section was prepared:

```yaml
medallion:
  enabled: true
  root_path: data/medallion
  bronze:
    enabled: true
    root_path: data/medallion/bronze
    max_payload_bytes: 262144
    require_original_first_write: true
  silver:
    enabled: true
    root_path: data/medallion/silver
    max_revision_bytes: 262144
    require_source_link: true
  gold:
    enabled: true
    root_path: data/medallion/gold
    require_versioned_build: true
    require_published_bundle: true
  publication:
    enabled: true
    require_complete_evidence: true
  admission:
    enabled: true
    require_explicit_acceptance: true
    reject_point_in_time_decision: true
  governance:
    enabled: true
    retention_days: 365
    require_final_audit: true
    require_exact_replay: true
  execution:
    mode: paper
    live_enabled: false
    require_explicit_user_authorization: true
    kill_switch_enforced: true
  expansion:
    enabled: true
    underlyings: [NIFTY, BANKNIFTY]
    stock_options_enabled: false
    stocks_enabled: false
    spreads_enabled: false
    multi_leg_strategies_enabled: false
```

This proposal is documentation/configuration design, not yet a wired runtime integration.


## 9. Dashboard scope

The current Dash dashboard is a read-only NIFTY paper-trading operations console.

It displays:

- Execution mode.
- Live trading blocked.
- Kill switch.
- Loop status.
- Strategy eligibility.
- Data quality.
- IV history.
- NIFTY spot, ATM IV, IV rank, IV-RV spread, PCR, expected move, and regime.
- IV smile.
- Market features.
- Open strategy positions.

It reads from `data/live_snapshot.json` through `read_live_snapshot()`.

The dashboard does not currently display the recent P0-P5 governance results.

`build_snapshot()` only accepts:

- features.
- open_positions.
- latest_orders.
- latest_exits.
- kill_switch_active.
- loop_status.
- data_quality.
- iv_history.
- strategy_eligibility.

It has no fields for P0-P5 governance results.

## 10. Dashboard integration proposal

To surface the recent governance work, add a read-only `native_governance` section to the dashboard.

Proposed cards:

| Gate | Displayed state |
|---|---|
| P0 | Evidence chain complete / execution complete |
| P1 | Gold/admission complete |
| P2 | Lifecycle/recovery complete |
| P3 | Operational acceptance complete |
| P4 | Controlled execution complete |
| P5 | Expansion complete |

Each card should show:

- Completed: Yes/No.
- Fingerprint: present/absent.
- Replay: passed/failed/not run.
- Eligibility asserted: False.
- Live trading: Blocked.
- Production cutover: Not authorized.

The dashboard must remain read-only with respect to trading.

## 11. Safety boundaries

The following boundaries remain mandatory:

- `POINT_IN_TIME_DECISION` remains rejected.
- `decision_eligibility_asserted` remains `False`.
- No eligibility, live trading, healing, backfill, adoption, deletion, production cutover, or execution authority is granted.
- Original failed, incomplete, unlinked, or orphan obligations are not healed by later success.
- Live execution requires explicit configuration and explicit user authorization.
- Package QA is not platform acceptance.

## 12. Operational holds

Data loading/migration remains held.

No live acquisition, user-data migration or backfill, real identity/key/policy/authority registration, production publication, trading, or decision-loop cutover is authorized.

## 13. How to run the platform

### 13.1 Install

```powershell
cd C:\Projects\nse_quant_platform
uv sync
```

### 13.2 Configure secrets

Create `.env`:

```env
KITE_API_KEY=your_kite_api_key
KITE_API_SECRET=your_kite_api_secret
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
```

### 13.3 Run QA

```powershell
uv run pytest tests/data_platform -q
uv run pytest tests -q
uv run ruff check .
uv run mypy .
git diff --check
```

### 13.4 Run paper loop

```powershell
uv run python -m nse_quant
```

### 13.5 Open dashboard

```text
http://127.0.0.1:8050
```

## 14. Decision record

The platform coding scope is complete across P0-P5.

The Medallion architecture is the foundation.

The recent P0-P5 work is the governance layer built on top of it.

The legacy paper loop remains the currently running application path.

The dashboard currently shows only legacy paper-loop operational data, not the recent P0-P5 governance results.

The recommended next architecture step is:

1. Keep contracts module-local.
2. Centralize only safe operational settings.
3. Create one shared calculation-primitives module.
4. Make `analytics`, `research`, and `data_platform` consume it.
5. Add a read-only native-governance dashboard section.

This preserves safety, removes drift, and prepares the platform for operational acceptance without authorizing production cutover.
--------------------------------------------------------------------------------------------------------------------------------

*_COMPLETED_ Sections*

**## 8. Analytics and research overlap

### 8.1 Three layers

| Layer | Folder | Purpose |
|---|---|---|
| Live decision loop | `src/nse_quant/analytics` | Live IV, RV, regime, features, greeks, decision analytics |
| Research/backtesting | `src/nse_quant/research` | IV surface, IV regimes, backtests, research reports |
| Medallion/native governance | `src/nse_quant/data_platform` | Evidence, Bronze/Silver/Gold, publication, admission, governance, replay |

### 8.2 Overlap

There is real overlap between `analytics` and `research` in:

- IV calculations.
- Black-Scholes and option analytics.
- Regime classification.
- Feature-like calculations.
- Time-to-expiry conventions.
- Risk-free-rate assumptions.

For example:

- `analytics/option_analytics.py` uses SciPy-based Black-Scholes and IV solving.
- `research/iv_surface.py` has its own Black-Scholes delta helper and hard-coded risk-free rate.
- `analytics/features.py` computes live IV rank and regime.
- `research/iv_regimes.py` classifies daily IV regimes from research data.

### 8.3 Risk

Parallel implementations can drift:

- Different IV definitions.
- Different regime definitions.
- Different Black-Scholes implementations.
- Different feature windows.
- Different time-to-expiry conventions.
- Different risk-free-rate assumptions.
- Divergent results between live loop, research, and Medallion evidence.

### 8.4 Recommended target

Keep three responsibilities, but remove calculation duplication:

```text
core
  -> shared calculation primitives

analytics
  -> live decision-loop features

research
  -> research and backtesting

data_platform
  -> Medallion evidence, governance, replay
```

Create one canonical calculation-primitives module for:

- Black-Scholes price.
- Black-Scholes greeks.
- Implied volatility.
- Time-to-expiry.
- Risk-free rate.
- IV rank.
- IV percentile.
- ATM IV.
- Realized volatility.
- Regime classification.

Then `analytics`, `research`, and `data_platform` should consume the same primitives rather than maintaining separate implementations.**