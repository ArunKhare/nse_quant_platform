# Multi-horizon NIFTY strategy profiles

`src/nse_quant/research/strategy_profiles.py` is a pure additive registry of six NIFTY strategy profiles across three horizons (intraday, swing, positional) and two structures (iron condor, butterfly).

## Contract

- `get_profile(profile_id)` returns a `StrategyProfile` or `None`.
- `list_profiles(horizon=..., underlying=...)` filters the registry.
- `list_horizons()` returns the distinct horizons.
- `profile_summary(profile)` / `all_profiles_summary()` return dict views with `decision_eligibility_asserted=False`.

## Safety

- Research registry only; no execution authority, no admission, no decision eligibility.
- `decision_eligibility_asserted=False` is a real dataclass field defaulting to False on every profile.
- Profiles reference allowed regimes but do not grant or gate anything.
