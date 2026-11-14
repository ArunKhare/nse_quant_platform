# Current native-platform status (multi-horizon addendum)

## Added

- Multi-horizon NIFTY strategy profiles (`src/nse_quant/research/strategy_profiles.py` + tests + docs): 6 profiles across intraday/swing/positional horizons and iron-condor/butterfly structures. `decision_eligibility_asserted` is now a real dataclass field defaulting to False.

## Unchanged

- All 8 evidence plugins, GATERESULTS SILVER, walk-forward, positions Silver, strategy_positions Silver remain implemented.
- All 7 open status gates remain open; this addendum does not close any gate.

## Holds

Data loading/migration held. No live acquisition, user-data migration or backfill, real identity/key/policy/authority registration, production publication, trading or decision-loop cutover authorized.
