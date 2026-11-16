

## 2026-11-16 addendum: risk-decisions Silver

Delivered (packaged, pending user QA): persisted source-linked `risk_decisions` Silver over the actual accepted Bronze reader.

- Store: `legacy-risk-decisions-silver-recording@1`
- Command: `normalize.legacy_risk_decisions@1`
- Contract: `silver.legacy_risk_decisions_observations@1` `APPEND_REVISIONS`
- Materialized: all 8 retained fields with exact nullability; `risk_decision_id` only key; per-revision uniqueness plus ordinal
- `approved` remains a nullable retained legacy claim, never native risk approval
- `reasons`/`checks` remain opaque retained JSON-cast text; SQL NULL distinct from JSON null
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No payload interpretation, admission, original risk replay, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.
