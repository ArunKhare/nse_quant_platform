# Multi-leg NIFTY strategy library

`src/nse_quant/research/multi_leg_library.py` is a pure additive registry of six multi-leg NIFTY strategy profiles across three horizons (intraday, swing, positional) and three structures (iron fly, calendar spread, ratio spread).

## Contract

- `get_profile(profile_id)` returns a `MultiLegProfile` or `None`.
- `list_profiles(horizon=..., structure=..., underlying=...)` filters the registry.
- `list_horizons()` / `list_structures()` return distinct values.
- `profile_summary(profile)` / `all_profiles_summary()` return dict views with `decision_eligibility_asserted=False`.

## Safety

- Research registry only; no execution authority, no admission, no decision eligibility.
- `decision_eligibility_asserted=False` is a real dataclass field defaulting to False on every profile.
- Profiles reference allowed regimes and leg composition but do not grant or gate anything.
