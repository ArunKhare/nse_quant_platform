# NIFTY directional defined-risk spread profiles

`src/nse_quant/research/spread_profiles.py` is a pure additive registry of six NIFTY directional spread profiles across three horizons (intraday, swing, positional) and two directions (BULLISH bull call spread, BEARISH bear put spread).

## Contract

- `get_profile(profile_id)` returns a `SpreadProfile` or `None`.
- `list_profiles(horizon=..., direction=..., underlying=...)` filters the registry.
- `list_horizons()` / `list_directions()` return distinct values.
- `profile_summary(profile)` / `all_profiles_summary()` return dict views with `decision_eligibility_asserted=False`.

## Safety

- Research registry only; no execution authority, no admission, no decision eligibility.
- `decision_eligibility_asserted=False` is a real dataclass field defaulting to False on every profile.
- Profiles carry descriptive `market_tags`; these tags are not canonical regime labels and do not grant or gate decision eligibility.
