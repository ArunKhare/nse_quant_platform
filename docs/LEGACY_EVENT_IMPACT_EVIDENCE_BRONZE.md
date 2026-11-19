# Legacy event impact evidence Bronze

Actual audited whole-table retained `event_impact_evidence` Bronze, never event truth.

## Contract

- Codec: `legacy-event-impact-evidence-snapshot@1`
- Observation: `legacy-event-impact-evidence-observation@1`
- Bronze: `legacy-event-impact-evidence-bronze-recording@1`
- Command: `migrate.legacy_event_impact_evidence@1`
- Source: `legacy_event_impact_evidence_table_snapshot`

## Retained schema

Thirteen columns, `impact_id` only key, all other fields nullable: `run_id`, `ts TIMESTAMPTZ`, `event_id`, `event_type`, `instrument`, `direction`, `volatility_impact`, `liquidity_impact`, `confidence DOUBLE`, `surprise_label`, `recommended_action`, `payload JSON`.

`ts` stays a stored TIMESTAMPTZ instant or unknown. `confidence` stays finite binary64 hex. `payload` stays opaque `CAST(JSON AS VARCHAR)`; SQL NULL stays distinct from JSON null.

## Native path

`capture_event_impact_evidence` verifies the exact base-table schema and bounded text budget, then produces a canonical whole-table snapshot. `preserve_event_impact_evidence` requires two identical captures, derives bounded observation records, and appends exactly one Bronze event with a separate audit job.

`read_event_impact_evidence_bronze` verifies the original variant, audit history, batch, and artifact before returning the derived records. `revalidate_event_impact_evidence_source` additionally re-captures the current source twice and compares against the retained recording.

This Bronze does not interpret direction, volatility/liquidity impact, surprise labels, or payloads as native event truth, replay event impact, or grant decision eligibility.
