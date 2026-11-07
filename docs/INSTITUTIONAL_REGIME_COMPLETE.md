# Institutional regime completion

`InstitutionalRegimePlugin` now computes all four components: `iv_state`, `term_structure`, `skew`, and `price_action`.

## Contract

- `compute_price_action` classifies completed candles into six states.
- `compute_skew` classifies put/call IV skew.
- When all four components are complete, the plugin assembles a regime label like `HIGH_IV_CONTANGO_NORMAL_SKEW_RANGE_UPPER`.
- When any component is incomplete, `regime_label` stays `None` and the reason names the first incomplete component.

## Safety

- Observational only; never grants decision eligibility.
- Never enables live trading.
- Regime label is not used for eligibility until the promotion checklist is satisfied.
