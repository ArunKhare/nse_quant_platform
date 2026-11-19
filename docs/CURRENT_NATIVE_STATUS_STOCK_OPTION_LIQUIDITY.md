# Current native-platform status (stock-option liquidity addendum)

## Added

- Stock-option liquidity thresholds (`src/nse_quant/research/stock_option_liquidity.py` + tests + docs): pure additive research evaluator consistent with Trading Universe Roadmap Phase 3. Test updated to use `pytest.approx` for float comparison on `spread_pct`.

## Unchanged

- All 8 evidence plugins, GATERESULTS SILVER, walk-forward, positions Silver, strategy_positions Silver, multi-horizon NIFTY strategy profiles, multi-day reliability evidence, vectorbt backtest adapter, event reaction recorder, NIFTY directional spread profiles, multi-leg strategy library, stock context features, cash-stock swing signal generator, corporate-actions calendar remain implemented.
- All 7 open status gates remain open; this addendum does not close any gate.

## Holds

Data loading/migration held. No live acquisition, user-data migration or backfill, real identity/key/policy/authority registration, production publication, trading or decision-loop cutover authorized.
