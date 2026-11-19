# Legacy spot candles and daily RV Silver

Persisted Silver derived only from the new-series Bronze recordings for `spot_candles` and `daily_rv_observations`.

## Contract

- Spot candles: `legacy-spot-candles-silver-recording@1`, command `persist.legacy_spot_candles_silver@1`
- Daily RV: `legacy-daily-rv-observations-silver-recording@1`, command `persist.legacy_daily_rv_observations_silver@1`
- Each Silver revision is bound to the exact reviewed Bronze recording fingerprint and context hash.

## Native path

`observe_*_bronze` reads the Bronze records through the public Bronze reader and derives a bounded context. `persist_*_silver` requires two identical Bronze observations, then writes one Silver set, one observation per Bronze record, and one attempt, all inside one transaction with a separate audit job.

The public reader verifies the Silver context hash, recording fingerprint, and per-record coverage. Current Bronze equality remains separate from persisted Silver replay.

Neither Silver layer interprets market data, proves validity, replays execution, or grants decision eligibility.
