# Analytics/Research Calculation Unification

## Status

Implementation-ready refactor bundle for Section 8.

## Changes

- `analytics/option_analytics.py` now delegates to canonical primitives.
- `analytics/features.py` now uses canonical IV rank, percentile, ATM IV, RV, and market regime.
- `research/iv_surface.py` now uses canonical Black-Scholes and time-to-expiry.
- Research now requires explicit `risk_free_rate`.
- Compatibility wrappers preserve existing analytics APIs.

## Canonical decisions

- Risk-free rate: `settings.analytics.risk_free_rate`, passed explicitly.
- Year basis: 365.25.
- IV solver: SciPy Brent, bounds 0.0001-5.0, xtol 1e-10.
- Market regime: spot/SMA/RV.
- IV regime: remains research-specific.

## Safety

No Medallion contract, admission, replay, or live-trading boundary is changed.
