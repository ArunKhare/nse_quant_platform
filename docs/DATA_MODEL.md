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
