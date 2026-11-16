

## 2026-11-16 addendum: orders Silver

Delivered (packaged, pending user QA): persisted source-linked `orders` Silver over the actual accepted Bronze reader.

- Store: `legacy-orders-silver-recording@1`
- Command: `normalize.legacy_orders@1`
- Contract: `silver.legacy_orders_observations@1` `APPEND_REVISIONS`
- Materialized: all 12 retained fields with exact nullability; `order_id` only key; per-revision uniqueness plus ordinal
- `limit_price`/`filled_price` remain retained finite binary64 values; `payload` remains opaque retained JSON-cast text
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No payload interpretation, execution replay, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.
