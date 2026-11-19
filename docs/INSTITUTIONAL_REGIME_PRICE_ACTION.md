# Institutional regime price-action component

`compute_price_action` classifies completed-candle price action into one of six states for the institutional regime plugin.

## Contract

- Input: closes, highs, lows lists and `InstitutionalRegimePriceActionSettings`.
- Output: one of six states (TREND_UP, TREND_DOWN, RANGE_UPPER, RANGE_MIDDLE, RANGE_LOWER, INSUFFICIENT_DATA).
- Safety: never asserts market truth, never grants decision eligibility, never enables live trading.

## Rules

- Missing or mismatched candles return INSUFFICIENT_DATA.
- A directional change must cross the trend threshold to classify as TREND_UP or TREND_DOWN.
- The trend threshold is the greater of the configured range band and the central range span after excluding both edge bands.
- Otherwise, final close position within twice the configured range band (capped at half the period range) classifies RANGE_UPPER or RANGE_LOWER; positions on the boundaries or between them classify RANGE_MIDDLE.
