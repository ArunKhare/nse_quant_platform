# Event-to-instrument impact mapping

`EventImpactMapper` turns reviewed scheduled `market_events` rows into bounded instrument-level impact evidence for the decision symbol.

## Contract

- Plugin: `event_impact`
- Input: `market_events` within the configured blackout window and ingested at or before the decision time
- Output: retained observational mappings; never event truth or execution authority
- Blocking: always `False`; this mapper observes, it does not gate

## Mapping rules

- `affected_underlyings` may be a JSON list or an object keyed by underlying.
- Object values may retain `direction`, `volatility_impact`, `liquidity_impact`, and `confidence`.
- List mappings retain the event reference but leave detail fields null.
- Malformed mapping text marks the result incomplete rather than fabricating a mapping.
- Confidence outside `0.0..1.0` is retained as null.

## Decision-loop integration

The mapper is registered in `DecisionLoop` only when both `evidence.enabled` and `evidence.plugins.event_impact.enabled` are true.

```yaml
evidence:
  plugins:
    event_impact:
      enabled: false
      blackout_minutes_before: 30
      blackout_minutes_after: 30
```

The default configuration keeps the mapper disabled. Enabling it adds observational evidence; it does not create a blocking gate or alter execution authorization.

## Safety

- `ingested_at <= decision_ts` prevents future-ingested records from leaking into historical evaluations.
- The mapper never interprets event truth, replays execution, or grants decision eligibility.
- `block_new_entries` remains `False`; blackout blocking remains the responsibility of `event_risk`.
