# Operations

## Daily startup

1. Confirm `.env` has valid Kite credentials.
2. Confirm `DRY_RUN=true`, `TRADING_ENABLED=false`, and `PAPER_TRADING=true`.
3. Run `uv run pytest`.
4. Run a bounded streaming validation.
5. Start the Dash console and paper decision loop.
6. Review risk state and kill switch before considering any future live mode.

## Shutdown

The loop closes WebSocket connections, flushes DuckDB batches, marks the run inactive, and writes
a final dashboard snapshot.

## Common checks

- No quote: inspect instrument token, subscription, and market hours.
- Stale quote: inspect WebSocket connectivity and `stale_seconds`.
- IV calculation failure: inspect LTP, spot, time to expiry, and option type.
- Risk rejection: inspect `decision_events`; rejections are valuable process data, not failures.

## Live decision-loop monitoring

Use these files for operational monitoring while the paper loop is running:

- `data/live_snapshot.json`: latest loop status, features, data quality, eligibility, positions, and orders.
- `logs/live_status.json`: latest candle-capture and loop-status heartbeat.
- `market_data/latest_stream.json`: WebSocket connection, tick count, and expiry coverage.

Do not query DuckDB directly while the scheduled paper loop holds the write lock.

### Required healthy state

- `live_snapshot.json` and `live_status.json` timestamps continue updating.
- `market_data/latest_stream.json` reports `connected: true` and increasing ticks.
- `data_quality.is_usable` is `true`.
- `realized_vol` is either `null` when insufficient history exists or a positive computed value.
- `iv_rv_spread` is `null` whenever `realized_vol` is unavailable.
- Strategy rejection reasons identify the active policy gate, such as `IV regime not allowed: BEAR|HIGH`.

### Known safeguards

- Spot-feature history uses the stored `1m` candle interval.
- Synthetic flat close history is not used when live candle history is unavailable.
- A zero or missing realized-volatility estimate does not produce a misleading IV-RV spread.