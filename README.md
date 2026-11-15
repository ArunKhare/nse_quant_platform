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
