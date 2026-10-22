# NSE Quant Scripts

Operational and research scripts for the NSE Quant Decision Platform.

All commands assume you are in the repository root:

```bash
cd /c/Projects/nse_quant_platform
```

## Daily operations

| Script | Purpose | How to run |
|---|---|---|
| `run_paper_loop.py` | Runs the paper decision loop: captures data, evaluates gates, creates proposals, and places paper orders when enabled. | `python scripts/run_paper_loop.py` |
| `loop_status.py` | Summarizes the latest loop cycle: features, regime, gates, proposal, orders, positions, exits, and expected-move diagnostics. | `python scripts/loop_status.py` |
| `iv_progress.py` | Reports IV-history, IV-RV alignment, and feature availability. | `python scripts/iv_progress.py` |
| `check_iv_capture.py` | Checks whether IV observations are being captured. | `python scripts/check_iv_capture.py` |
| `run_dashboard.py` | Starts the local dashboard. | `python scripts/run_dashboard.py` |
| `start_paper_loop.ps1` | Windows PowerShell helper for starting the paper loop. | `powershell -File scripts/start_paper_loop.ps1` |
| `start_eod_maintenance.ps1` | Windows PowerShell helper for end-of-day maintenance. | `powershell -File scripts/start_eod_maintenance.ps1` |

### Paper loop testing

Use these flags only for controlled out-of-hours testing:

```bash
python scripts/run_paper_loop.py --seconds 60 --config config/settings.test.yaml --allow-out-of-hours --allow-stale-features
```

Then inspect the result:

```bash
python scripts/loop_status.py --config config/settings.test.yaml
```

## Data backfill and maintenance

| Script | Purpose | How to run |
|---|---|---|
| `backfill_candles.py` | Backfills historical spot candles. | `python scripts/backfill_candles.py --symbol NIFTY --interval 1m --from 2026-10-20 --to 2026-10-23` |
| `backfill_iv.py` | Backfills historical IV observations. | `python scripts/backfill_iv.py --symbol NIFTY` |
| `backfill_option_iv.py` | Backfills option-level IV data. | `python scripts/backfill_option_iv.py --symbol NIFTY` |
| `backfill_option_greeks.py` | Backfills option Greeks. | `python scripts/backfill_option_greeks.py --symbol NIFTY` |
| `backfill_market_regime_exports.py` | Backfills exported market-regime policy data. | `python scripts/backfill_market_regime_exports.py --symbol NIFTY` |
| `bootstrap_nse_eod_iv.py` | Bootstraps end-of-day IV history. | `python scripts/bootstrap_nse_eod_iv.py --symbol NIFTY` |
| `fill_data_gaps.py` | Identifies and fills missing warehouse data. | `python scripts/fill_data_gaps.py --symbol NIFTY` |
| `eod_maintenance.py` | Runs end-of-day warehouse and feature maintenance. | `python scripts/eod_maintenance.py --symbol NIFTY` |
| `import_candle.py` | Imports a candle file into the warehouse. | `python scripts/import_candle.py --help` |
| `build_daily_candles.py` | Builds daily candles from intraday data. | `python scripts/build_daily_candles.py --symbol NIFTY` |
| `build_daily_rv.py` | Builds daily realized-volatility observations. | `python scripts/build_daily_rv.py --symbol NIFTY` |
| `build_spot_features.py` | Builds spot features, including ATR and trend indicators. | `python scripts/build_spot_features.py --symbol NIFTY --from 2026-10-13 --to 2026-10-23` |
| `build_market_regimes.py` | Builds daily market regimes from trend, volatility, and IV data. | `python scripts/build_market_regimes.py --symbol NIFTY --from 2026-08-01 --to 2026-10-23` |
| `build_single_expiry_iv.py` | Builds IV data for one option expiry. | `python scripts/build_single_expiry_iv.py --help` |

## Research and reporting

| Script | Purpose | How to run |
|---|---|---|
| `iv_surface_report.py` | Reports IV surface and term-structure characteristics. | `python scripts/iv_surface_report.py --symbol NIFTY` |
| `classify_iv_regimes.py` | Classifies historical IV-surface regimes. | `python scripts/classify_iv_regimes.py --symbol NIFTY` |
| `build_research_panel.py` | Builds the research panel used for regime and strategy analysis. | `python scripts/build_research_panel.py --symbol NIFTY` |
| `export_daily_rv.py` | Exports daily realized volatility. | `python scripts/export_daily_rv.py --symbol NIFTY` |
| `export_replay.py` | Exports a chain-snapshot replay file. | `python scripts/export_replay.py --help` |
| `export_active_policy.py` | Exports the active regime policy. | `python scripts/export_active_policy.py --symbol NIFTY` |
| `regime_coverage_report.py` | Reports market-regime coverage and data completeness. | `python scripts/regime_coverage_report.py --symbol NIFTY` |
| `regime_policy_status.py` | Reports the latest learned regime-policy status. | `python scripts/regime_policy_status.py --symbol NIFTY` |
| `evaluate_regime_policy.py` | Evaluates a learned regime policy. | `python scripts/evaluate_regime_policy.py --symbol NIFTY` |
| `walk_forward_regimes.py` | Runs walk-forward regime-policy research. | `python scripts/walk_forward_regimes.py --symbol NIFTY` |
| `run_milestone2_research.py` | Runs the Milestone 2 research workflow. | `python scripts/run_milestone2_research.py --symbol NIFTY` |
| `warehouse_quality_report.py` | Reports warehouse data-quality issues. | `python scripts/warehouse_quality_report.py` |
| `validate_warehouse.py` | Validates warehouse tables and completeness. | `python scripts/validate_warehouse.py` |
| `load_warehouse.py` | Loads Parquet or external data into the warehouse. | `python scripts/load_warehouse.py --help` |

## Backtesting

| Script | Purpose | How to run |
|---|---|---|
| `backtest_iron_condor.py` | Backtests the iron-condor strategy. | `python scripts/backtest_iron_condor.py --symbol NIFTY` |
| `backtest_readiness.py` | Checks whether enough data exists for backtesting. | `python scripts/backtest_readiness.py --symbol NIFTY` |
| `backtest_report.py` | Produces a backtest performance report. | `python scripts/backtest_report.py --help` |
| `build_backtest_returns.py` | Builds backtest return series. | `python scripts/build_backtest_returns.py --symbol NIFTY` |
| `run_replay_backtest.py` | Replays a saved chain snapshot through the decision loop. | `python scripts/run_replay_backtest.py --help` |
| `sweep_iron_condor.py` | Sweeps iron-condor parameters. | `python scripts/sweep_iron_condor.py --symbol NIFTY` |

## Debugging

| Script | Purpose | How to run |
|---|---|---|
| `debug_iron_condor.py` | Debugs iron-condor proposal generation and gates. | `python scripts/debug_iron_condor.py --symbol NIFTY` |
| `debug_option_stream.py` | Debugs live option-stream capture. | `python scripts/debug_option_stream.py` |
| `decision_report.py` | Prints a human-readable decision report. | `python scripts/decision_report.py --help` |
| `run_platform.py` | Starts the combined platform entry point. | `python scripts/run_platform.py --help` |
| `run_stream_check.py` | Checks live market-data streaming. | `python scripts/run_stream_check.py` |

## Important safety notes

- `run_paper_loop.py` uses `PaperBroker`; it does not place live Kite orders.
- Live trading remains blocked while `trading_enabled` is `false`.
- Use `--allow-out-of-hours` and `--allow-stale-features` only for controlled testing.
- Do not use stale-feature testing for live decision-making.
- Keep production `config/settings.yaml` conservative; use `config/settings.test.yaml` for relaxed test thresholds.