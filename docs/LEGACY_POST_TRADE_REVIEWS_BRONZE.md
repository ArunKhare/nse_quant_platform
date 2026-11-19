# Legacy post-trade reviews Bronze

Audited preservation of the complete retained `main.post_trade_reviews` base table.

## Contract

- Codec: `legacy-post-trade-reviews-snapshot@1`
- Projection: `legacy-post-trade-review-observation@1`
- Recording: `legacy-post-trade-reviews-bronze-recording@1`
- Command: `migrate.legacy_post_trade_reviews@1`
- Source: `legacy_post_trade_reviews_table_snapshot`, `origin_kind=legacy_snapshot`

## Retained source

The exact ten-column source is retained: `review_id` sole primary key; nullable aware `ts`; nullable `strategy_position_id`, `proposal_id`, and `strategy`; finite binary64 `realized_pnl`; nullable `exit_reason`, `thesis_status`, `decision_quality_notes`, and `outcome_notes`.

No natural key is invented. `ts` remains a nullable aware SQL instant, not availability or execution truth. `exit_reason` and `thesis_status` remain retained labels, not authenticated native exit or outcome truth. `realized_pnl` remains a retained finite binary64 value encoded exactly as hex, not economic-validity evidence. Notes remain exact nullable text; empty text and SQL `NULL` remain distinct.

## Native path

`capture_post_trade_reviews` captures the entire exact-schema base table in one source transaction, with SQL count/text preflight, independent cell guards, and a max-plus-one row bound. `preserve_post_trade_reviews` performs two complete captures, verifies the reviewed snapshot pin, derives and bounds every projected record before append, and writes one event/artifact/batch through the actual native Bronze store and audit ledger.

The public reader verifies the original envelope, source/session scope, complete artifact, original batch, scoped job, and exact audit history. Current legacy SQL equality remains separate from retained native replay.

This package does not recover overwritten history or original provider bytes, interpret P&L or notes, prove outcomes, replay review execution, assert availability or economic validity, publish research, or grant decision eligibility.
