# Market-session evidence

`classify_market_session` classifies a decision timestamp into a market-session state using IST regular session boundaries.

## Contract

- Input: timezone-aware decision timestamp and `MarketSessionSettings`.
- Output: state (`PRE_MARKET`, `REGULAR_SESSION`, `POST_MARKET`, `CLOSED`), optional `eligible_for_entry`.
- Safety: never asserts market truth, never grants decision eligibility, never enables live trading.

## Rules

- Weekend returns `CLOSED`.
- Before 09:15 IST returns `PRE_MARKET`.
- Between 09:15 and close returns `REGULAR_SESSION`.
- After close returns `POST_MARKET`.
- `eligible_for_entry` is only set when `require_regular_session` is true.
