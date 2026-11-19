# Current native-platform status (cash-stock swing addendum)

## Added

- Cash-stock swing strategy signal generator (`src/nse_quant/research/cash_stock_swing.py` + tests + docs): pure additive research signal generator consistent with Trading Universe Roadmap Phase 2. `compute_rvol` now excludes the current row from the baseline (shift(1)) to avoid look-ahead.

## Unchanged

- All 8 evidence plugins, GATERESULTS SILVER, walk-forward, positions Silver, strategy_positions Silver, multi-horizon NIFTY strategy profiles, multi-day reliability evidence, vectorbt backtest adapter, event reaction recorder, NIFTY directional spread profiles, multi-leg strategy library, stock context features remain implemented.
- All 7 open status gates remain open; this addendum does not close any gate.

## Holds

Data loading/migration held. No live acquisition, user-data migration or backfill, real identity/key/policy/authority registration, production publication, trading or decision-loop cutover authorized.
