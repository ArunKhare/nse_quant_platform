# Legacy risk-decisions Silver

Persisted, source-linked Silver over the actual accepted `risk_decisions` Bronze reader.

- Store: `legacy-risk-decisions-silver-recording@1`
- Command: `normalize.legacy_risk_decisions@1`
- Contract: `silver.legacy_risk_decisions_observations@1` `APPEND_REVISIONS`
- Source: `main.risk_decisions`, 8 columns, `risk_decision_id` only key
- Materialized: `risk_decision_id`, nullable `ts` (`TIMESTAMPTZ`), `run_id`, `proposal_id`, `strategy`, nullable `approved` (`BOOLEAN`), opaque `reasons`/`checks` (`VARCHAR` from retained JSON-cast text)
- SQL `NULL` stays distinct from JSON `null` text; `False`/`None`/`True` stay distinct
- Per-revision `risk_decision_id` uniqueness plus ordinal; no invented natural key
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- SQL scalar/record/aggregate byte preflight before transfer
- `approved=True` is a retained legacy claim, never native risk approval, safety truth, or execution permission
- No payload interpretation, admission, original risk replay, or positive decision eligibility
