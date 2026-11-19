# Institutional regime label assembly

`InstitutionalRegimePlugin.build()` now assembles `regime_label` when all four components are complete.

## Contract

- Composes label as `{iv_state}_{term_structure}_{skew}_{price_action}`.
- Example: `HIGH_IV_CONTANGO_NORMAL_SKEW_RANGE_UPPER`.
- When any component is incomplete, `regime_label` stays `None` and `complete` stays `False`.
- `reason` names the first incomplete component.

## Safety

- Observational only; never grants decision eligibility.
- Never enables live trading.
