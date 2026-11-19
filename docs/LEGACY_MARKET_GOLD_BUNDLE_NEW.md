# Legacy market Gold bundle

Audited Gold bundle combining the five completed per-table Gold recordings into one cross-table snapshot.

## Contract

- Recording: `legacy-market-gold-bundle-recording@1`
- Command: `persist.legacy_market_gold_bundle@1`
- Members: `spot_candles`, `spot_features`, `market_regimes`, `underlying_iv`, `daily_rv`
- Each bundle revision is bound to the exact reviewed Gold recording fingerprint, all five Gold revision ids, and the bundle context hash.

## Native path

`observe_market_gold_bundle` reads each member Gold recording through its public Gold reader and derives a bounded context. `persist_market_gold_bundle` requires two identical bundle observations, then writes one bundle set, one observation per member record, and one attempt, all inside one transaction with a separate audit job.

The public reader verifies the bundle context hash, recording fingerprint, and per-member/per-record coverage. Current Gold equality remains separate from persisted bundle replay.

This bundle does not interpret market data, prove validity, replay execution, or grant decision eligibility.
