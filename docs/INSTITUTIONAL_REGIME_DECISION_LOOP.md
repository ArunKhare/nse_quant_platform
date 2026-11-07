# Institutional regime decision-loop integration

`register_institutional_regime` appends `InstitutionalRegimePlugin` to the evidence plugin list so regime evidence is produced per decision cycle.

## Contract

- `build_institutional_regime_plugin` constructs the plugin from store and settings.
- `register_institutional_regime` appends idempotently (no duplicate registration).
- Safety: never grants decision eligibility, never enables live trading.

## Prerequisite

Apply `institutional-regime-label-assembly.zip` and `institutional-regime-persistence.zip` first so the plugin produces a non-null `regime_label` and persists evidence.
