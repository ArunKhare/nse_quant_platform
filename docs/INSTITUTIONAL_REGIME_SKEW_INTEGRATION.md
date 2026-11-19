# Institutional regime skew integration

`InstitutionalRegimePlugin` now computes the `skew` component via `compute_skew` from `institutional_regime_skew.py`.

## Contract

- Extracts ATM put IV and call IV from the current `ChainSnapshot`.
- Calls `compute_skew` with the plugin's skew settings.
- Replaces the former `not_implemented` placeholder for `skew`.
- `price_action` remains `not_implemented`.

## Safety

- Observational only; never grants decision eligibility.
- Never enables live trading.
