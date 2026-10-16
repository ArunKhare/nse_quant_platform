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
