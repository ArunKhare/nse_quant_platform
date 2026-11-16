# Legacy orders Silver

Persisted, source-linked Silver over the actual accepted `orders` Bronze reader.

- Store: `legacy-orders-silver-recording@1`
- Command: `normalize.legacy_orders@1`
- Contract: `silver.legacy_orders_observations@1` `APPEND_REVISIONS`
- Source: `main.orders`, 12 columns, `order_id` only key
- Materialized: `order_id`, nullable `ts`/`filled_at` (`TIMESTAMPTZ`), `run_id`, `proposal_id`, `strategy`, `broker`, `status`, nullable `limit_price`/`filled_price` (`DOUBLE`), `reject_reason`, opaque `payload` (`VARCHAR` from retained JSON-cast text)
- SQL `NULL` stays distinct from JSON `null` text
- Per-revision `order_id` uniqueness plus ordinal; no invented natural key
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- SQL scalar/record/aggregate byte preflight before transfer
- Retained order is not execution permission, broker truth, fill proof, or admission
- No payload interpretation, execution replay, or positive decision eligibility
