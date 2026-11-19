# Current native-platform status (vectorbt addendum)

## Added

- vectorbt backtest adapter (`src/nse_quant/research/backtest/vectorbt_adapter.py` + tests + docs): pure additive research-only bridge from existing BacktestResult equity curve or trade list to vectorbt Portfolio metrics.

## Unchanged

- All 8 evidence plugins, GATERESULTS SILVER, walk-forward, positions Silver, strategy_positions Silver, multi-horizon NIFTY strategy profiles, multi-day reliability evidence remain implemented.
- All 7 open status gates remain open; this addendum does not close any gate.

## Holds

Data loading/migration held. No live acquisition, user-data migration or backfill, real identity/key/policy/authority registration, production publication, trading or decision-loop cutover authorized.
