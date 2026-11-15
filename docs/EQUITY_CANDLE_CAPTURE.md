# Equity candle capture

`src/nse_quant/market_data/equity_candles.py` captures daily equity candles for
the cash-stock watchlist, consistent with the Trading Universe Roadmap Phase 2.

## Contract

- `EQUITY_WATCHLIST` — 10 liquid NSE large caps (RELIANCE, HDFCBANK, ICICIBANK, INFY, TCS, SBIN, AXISBANK, TATAMOTORS, MARUTI, SUNPHARMA).
- `write_equity_candles(store, symbol, candles, instrument_token)` — persists daily candles to the `spot_candles` table with `instrument_type='equity'`.
- `read_equity_candles(store, symbol, from_date, to_date)` — reads daily equity candles for one symbol.
- `ensure_equity_candle_schema(store)` — adds the `instrument_type` column if missing.

## Safety

- Research-only; no execution authority, no admission, no decision eligibility.
- Reuses the existing `spot_candles` table; no new table needed.
