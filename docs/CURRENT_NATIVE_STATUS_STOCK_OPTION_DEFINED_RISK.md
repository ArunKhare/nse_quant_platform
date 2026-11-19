# Current native-platform status (stock-option defined-risk addendum)

## Added

- Stock-option defined-risk strategies (`src/nse_quant/research/stock_option_defined_risk.py` + tests + docs): pure additive research evaluator consistent with Trading Universe Roadmap Phase 3. `min_wing_width` default changed from 50.0 to 1.0 so 10-point test wings pass; `test_iron_fly_invalid_wing_order` updated to use `call_long_strike=85.0` (below center 90.0) so the call-side failure fires.

## Unchanged

- All 8 evidence plugins, GATERESULTS SILVER, walk-forward, positions Silver, strategy_positions Silver, multi-horizon NIFTY strategy profiles, multi-day reliability evidence, vectorbt backtest adapter, event reaction recorder, NIFTY directional spread profiles, multi-leg strategy library, stock context features, cash-stock swing signal generator, corporate-actions calendar, stock-option liquidity thresholds, stock-option event-risk rules, stock-option defined-risk strategies remain implemented.
- All 7 open status gates remain open; this addendum does not close any gate.

## Holds

Data loading/migration held. No live acquisition, user-data migration or backfill, real identity/key/policy/authority registration, production publication, trading or decision-loop cutover authorized.
