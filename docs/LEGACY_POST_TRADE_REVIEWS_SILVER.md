# Legacy post-trade reviews Silver

Persisted source-linked post-trade-reviews Silver over the actual accepted Bronze reader.

## Contract

- Store: `legacy-post-trade-reviews-silver-recording@1`
- Command: `normalize.legacy_post_trade_reviews@1`
- Contract: `silver.legacy_post_trade_reviews /1/APPEND_REVISIONS`
- Each Silver revision is bound to the exact reviewed Bronze recording fingerprint and context hash.

## Retained materialization

All ten source fields are materialized with exact nullability: `review_id VARCHAR NOT NULL`; nullable `ts TIMESTAMPTZ`; nullable `realized_pnl DOUBLE`; nullable `strategy_position_id`, `proposal_id`, `strategy`, `exit_reason`, `thesis_status`, `decision_quality_notes`, and `outcome_notes VARCHAR`.

No invented natural key: only per-revision `review_id` uniqueness plus ordinal. `exit_reason` and `thesis_status` stay opaque nullable legacy labels, not native exit or outcome truth. PnL stays retained binary64, not interpreted trading truth. Notes stay exact nullable text.

## Native path

`observe_post_trade_reviews_bronze` reads Bronze records through the public Bronze reader and derives a bounded context. `persist_post_trade_reviews_silver` requires two identical Bronze observations, then writes one Silver set, one observation per Bronze record, and one attempt, all inside one transaction with a separate audit job.

The public reader verifies the Silver context hash, recording fingerprint, and per-record coverage. Current Bronze equality remains separate from retained Silver replay.

This Silver does not interpret PnL or notes, replay review execution, or grant decision eligibility.
