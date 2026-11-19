# Native analytics input validation

`validate_analytics_inputs` validates a dict of analytics inputs (feature inputs, thresholds) against a defined schema.

## Contract

- Input: inputs dict (feature_names, thresholds, history_window, cold_start_policy), `AnalyticsInputSchema`.
- Output: `AnalyticsValidation` with valid, reasons, checks.
- Safety: never grants eligibility, never enables live trading.

## Rules

- Feature names must be non-empty strings.
- Thresholds must be numeric and non-negative.
- History window must be non-negative int.
- Cold-start policy must be one of reject/warn/allow.
- Addresses the "native analytics inputs beyond the 9 requirements" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
