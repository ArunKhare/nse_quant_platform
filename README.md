# NSE Quant Decision Platform

A Python-based quantitative decision platform for NSE index options, cash stocks,
and stock options. The platform follows a medallion-style data architecture:
received artifacts -> immutable Bronze -> typed source-linked Silver -> versioned
Gold -> published bundles -> native decisions and exact replay.

## Status

- Core NIFTY paper decision loop is implemented and user-QA-confirmed.
- Research depth (warehouse, IV/RV research, replay backtests, QuantStats,
  experiments) is implemented.
- Controlled execution (Kite order placement, reconciliation, margin, partial
  fills, rule-based exits) remains roadmap work.
- All additive research modules are observational only and do not grant decision
  eligibility or execution authority.
- Live trading, production publication, and decision-loop cutover remain held.

Native Gate 6 increments now include persisted audited decision-run coverage
reconciliation Silver, an end-to-end native iron-condor decision-run pipeline,
authoritative identity/time validation, coverage evidence-link validation,
decision-loop integration, evidence-completeness validation, and end-to-end
acceptance tests.

Recent native-platform increments also include:

- Availability and economic-validity evidence validation.
- Gold decision publication candidate validation.
- Eligible admission contract evaluation.
- Lifecycle-recovery observations.
- Operational acceptance harness.
- Controlled execution gateway with paper-only default behavior.
- Multi-underlying expansion validation for NIFTY and BANKNIFTY.
- Native authority-evidence completeness-report audit-trail policy and replay.
- Native authority-evidence completeness-report audit-trail final audit and replay.
- Native authority-evidence completeness-report audit-trail enforcement and replay.
- Native authority-evidence completeness-report audit-trail persistence and replay.
- Native authority-evidence completeness-report audit-trail retention and expiry governance.
- Native authority-evidence completeness-report audit-trail archival and closure governance.
- Native authority-evidence completeness-report audit-trail query and export governance.
- Native authority-evidence completeness-report audit-trail import, round-trip, acceptance, and reconciliation governance.
- Native authority-evidence completeness-report audit-trail end-to-end lifecycle acceptance.

Authority-evidence audit-trail import, round-trip, acceptance, and
reconciliation governance imports exported audit trails exactly, performs
non-destructive round-trip replay, and governs acceptance and reconciliation.
It preserves the complete fingerprint chain and lifecycle without healing,
deletion, eligibility grants, or execution authority.

These increments remain observational. They do not close any native status gate,
grant decision eligibility, authorize live trading, or authorize healing,
backfill, adoption, or execution. `POINT_IN_TIME_DECISION` remains rejected.

See `docs/CURRENT_NATIVE_STATUS.md` for the authoritative current status,
remaining gates, and operational holds.

## Architecture

- `src/nse_quant/` — application and research code.
- `src/nse_quant/data_platform/` — medallion data-platform modules (Bronze,
  Silver, Gold, publication, admission, refusal, lifecycle).
- `src/nse_quant/research/` — pure additive research evaluators and signal
  generators (cash-stock swing, corporate actions, stock-option liquidity,
  event risk, defined-risk strategies, execution quality, launch readiness).
- `src/nse_quant/persistence/` — DuckDB persistence layer.
- `tests/` — pytest test suite (data platform, research, and more).
- `docs/` — per-module contracts, status addenda, and roadmap documents.
- `config/` — YAML settings (base and test).

## Key research modules

| Module | Purpose | Safety |
|---|---|---|
| `cash_stock_swing` | SMA/breakout/RVOL/ATR swing signal generator | Research only, no execution authority |
| `corporate_actions_calendar` | Dividends, splits, bonuses, buybacks, earnings blackout | Research registry only |
| `stock_option_liquidity` | Spread/depth/OI/volume tradability evaluator | Observational only |
| `stock_option_event_risk` | Earnings blackout, size reduction, short-vol block | Observational only |
| `stock_option_defined_risk` | Bull call / bear put / iron condor / iron fly validator | Observational only |
| `stock_option_execution_quality` | Quote age, spread, depth, risk-reward, slippage, time-to-event | Observational only |
| `stock_option_launch_readiness` | Combines liquidity + event risk + structure + execution quality | Observational only |

Every research module returns `decision_eligibility_asserted=False`.

## Setup

Requires Python >= 3.12 and `uv`.

```powershell
uv sync
uv run pytest tests -q
```

## QA commands

```powershell
uv run pytest tests/data_platform -q
uv run pytest tests -q
uv run ruff check .
uv run mypy .
git diff --check
```

## Safety boundary

- Persistent kill switch.
- Paper-only mode.
- Dry-run behavior.
- Market-hours enforcement.
- Data-quality gates.
- Liquidity gates.
- Per-strategy risk limits.
- Portfolio-level exposure limits.
- EOD review and warehouse exports.

A new strategy must never bypass these controls.

## Documentation

- `docs/CURRENT_NATIVE_STATUS.md` — authoritative current status, gates, holds.
- `docs/ROADMAP.md` — milestone roadmap.
- `docs/TRADING_UNIVERSE_ROADMAP.md` — instrument-family expansion plan.
- `docs/FUTURE_IMPLEMENTATION.md` — future configuration designs.
- Per-module docs in `docs/` for each research evaluator and data-platform family.
- `docs/CURRENT_NATIVE_STATUS_GATE6.md` — Gate 6 reconciliation, decision-loop,
  identity/time, evidence-link, evidence-completeness, and acceptance-test
  addendum.
- `docs/CURRENT_NATIVE_STATUS_2026-11-17_ADDENDUM.md` — 2026-11-17 native
  decision-run, Gold publication, admission, lifecycle recovery, operational
  acceptance, controlled execution gateway, and multi-underlying expansion
  addendum.
