# Current native-platform status (spreads addendum)

## Added

- NIFTY directional defined-risk spread profiles (`src/nse_quant/research/spread_profiles.py` + tests + docs): 6 profiles across intraday/swing/positional horizons and BULLISH/BEARISH directions (bull call spread, bear put spread). `decision_eligibility_asserted` is a real dataclass field defaulting to False.

## Unchanged

- All 8 evidence plugins, GATERESULTS SILVER, walk-forward, positions Silver, strategy_positions Silver, multi-horizon NIFTY strategy profiles, multi-day reliability evidence, vectorbt backtest adapter, event reaction recorder remain implemented.
- All 7 open status gates remain open; this addendum does not close any gate.

## Holds

Data loading/migration held. No live acquisition, user-data migration or backfill, real identity/key/policy/authority registration, production publication, trading or decision-loop cutover authorized.
