# Data model

## DuckDB tables

### option_stream

Append-only normalized option-chain ticks and analytics.

| Column | Type | Notes |
|---|---|---|
| run_id | VARCHAR | Streaming/decision-loop run |
| ts | TIMESTAMPTZ | IST snapshot time |
| underlying | VARCHAR | NIFTY, BANKNIFTY |
| expiry | DATE | Contract expiry |
| strike | DOUBLE | Strike price |
| option_type | VARCHAR | CE or PE |
| tradingsymbol | VARCHAR | Kite symbol |
| instrument_token | BIGINT | Kite token |
| lot_size | INTEGER | From instrument master |
| spot | DOUBLE | Underlying spot |
| ltp | DOUBLE | Option last traded price |
| bid / ask | DOUBLE | Best quotes |
| volume / oi | BIGINT | Liquidity and positioning |
| iv / delta / gamma / vega / theta | DOUBLE | Analytics |
| quote_status | VARCHAR | ready, stale, missing, invalid |
| payload_json | JSON | Full normalized tick |

### decision_events

| Field | Purpose |
|---|---|
| event_id | Unique event ID |
| ts | IST timestamp |
| run_id | Loop run |
| event_type | feature_snapshot, signal, risk_rejection, order_request, fill, exit, review |
| strategy | Strategy name |
| symbol / expiry | Contract context |
| proposal_json | Full proposal |
| decision_json | Gate/risk/execution result |
| reason | Human-readable reason |

### paper_orders / paper_positions

Order state and open/closed position state, including entry thesis, planned exit, realized P&L,
and review fields.

## Event retention

Raw option_stream data can be exported to Parquet by date and compacted periodically. Decision
events are retained longer because they are the audit trail for process quality.

## v0.3.0 persistence model

The platform stores intraday data first. Daily aggregates are derived views.

### Core tables

- `option_stream`: normalized option quotes and Greeks per snapshot.
- `feature_snapshots`: timestamped intraday market features.
- `decisions`: feature snapshots, signals, no-proposal outcomes, dry-run skips, and kill-switch events.
- `gate_results`: individual pre-trade gate outcomes.
- `risk_decisions`: independent risk approval or rejection.
- `orders`: paper order lifecycle.
- `strategy_positions`: logical multi-leg strategy group.
- `positions`: one independent row per option leg.
- `exit_events`: every triggered exit reason and the selected highest-priority reason.
- `post_trade_reviews`: separated decision-quality and trade-outcome notes.

### Position granularity

An iron condor is one `strategy_positions` row and four independent `positions` rows.
Each leg retains its own instrument, side, quantity, entry, mark, P&L, status, and exit reason.
