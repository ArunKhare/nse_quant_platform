# Legacy underlying IV Gold

Persisted Gold derived only from the reviewed `underlying-iv-observations` Silver recording.

## Contract

- Recording: `legacy-underlying-iv-gold-recording@1`
- Command: `persist.legacy_underlying_iv_gold@1`
- Each Gold revision is bound to the exact reviewed Silver recording fingerprint, Silver revision id, and context hash.

## Native path

`observe_underlying_iv_silver` reads Silver records through the public Silver reader and derives a bounded context. `persist_underlying_iv_gold` requires two identical Silver observations, then writes one Gold set, one observation per Silver record, and one attempt, all inside one transaction with a separate audit job.

The public reader verifies the Gold context hash, recording fingerprint, and per-record coverage. Current Silver equality remains separate from persisted Gold replay.

This Gold layer does not interpret IV or spot, prove validity, replay execution, or grant decision eligibility.
