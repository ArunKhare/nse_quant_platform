# Legacy daily RV Gold

Persisted Gold derived only from the reviewed `daily-rv-observations` Silver recording.

## Contract

- Recording: `legacy-daily-rv-gold-recording@1`
- Command: `persist.legacy_daily_rv_gold@1`
- Each Gold revision is bound to the exact reviewed Silver recording fingerprint, Silver revision id, and context hash.

## Native path

`observe_daily_rv_silver` reads Silver records through the public Silver reader and derives a bounded context. `persist_daily_rv_gold` requires two identical Silver observations, then writes one Gold set, one observation per Silver record, and one attempt, all inside one transaction with a separate audit job.

The public reader verifies the Gold context hash, recording fingerprint, and per-record coverage. Current Silver equality remains separate from persisted Gold replay.

This Gold layer does not interpret volatility, prove validity, replay execution, or grant decision eligibility.
