# Legacy decision-evidence Silver (materialized)

Persisted, source-linked materialized Silver over the actual accepted `decision_evidence` Bronze reader.

- Store: `legacy-decision-evidence-silver-materialized@1`
- Command: `normalize.legacy_decision_evidence@1`
- Contract: `silver.legacy_decision_evidence_materialized_observations@1` `APPEND_REVISIONS`
- Source: `main.decision_evidence`, 7 columns; natural key `(run_id, ts, symbol, plugin)`
- Materialized: `evidence_id`, `run_id`, wall-clock `ts` (`TIMESTAMP`, no timezone conversion), `symbol`, `plugin`, nullable `available` (`BOOLEAN`), nullable opaque `payload_json` (`VARCHAR`)
- Per-revision natural-key uniqueness plus ordinal; no invented single natural key
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- SQL scalar/record/aggregate byte preflight before transfer
- Retained evidence is not availability proof, decision eligibility, or admission
- No payload interpretation, timezone inference, or positive decision eligibility
