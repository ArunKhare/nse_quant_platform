# Legacy spot features Silver

Persisted Silver derived only from the new-series `spot-features` Bronze recording.

## Contract

- Recording: `legacy-spot-features-silver-recording@1`
- Command: `persist.legacy_spot_features_silver@1`
- Each Silver revision is bound to the exact reviewed Bronze recording fingerprint and context hash.

## Native path

`observe_spot_features_bronze` reads Bronze records through the public Bronze reader and derives a bounded context. `persist_spot_features_silver` requires two identical Bronze observations, then writes one Silver set, one observation per Bronze record, and one attempt, all inside one transaction with a separate audit job.

The public reader verifies the Silver context hash, recording fingerprint, and per-record coverage. Current Bronze equality remains separate from persisted Silver replay.

This Silver layer does not interpret features, prove validity, replay execution, or grant decision eligibility.
