

## 2026-11-16 addendum: decision-evidence Silver (materialized)

Delivered (packaged, pending user QA): persisted source-linked materialized `decision_evidence` Silver over the actual accepted Bronze reader.

- Store: `legacy-decision-evidence-silver-materialized@1`
- Command: `normalize.legacy_decision_evidence@1`
- Contract: `silver.legacy_decision_evidence_materialized_observations@1` `APPEND_REVISIONS`
- Materialized: `evidence_id`, `run_id`, wall-clock `ts` (`TIMESTAMP`), `symbol`, `plugin`, nullable `available`, nullable opaque `payload_json`
- Natural key `(run_id, ts, symbol, plugin)`; per-revision uniqueness plus ordinal
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No payload interpretation, timezone inference, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.
