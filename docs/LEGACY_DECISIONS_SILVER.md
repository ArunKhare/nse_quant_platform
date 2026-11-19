# Legacy decisions Silver

Persisted, source-linked Silver over the actual accepted `decisions` Bronze reader.

- Store: `legacy-decisions-silver-recording@1`
- Command: `normalize.legacy_decisions@1`
- Contract: `silver.legacy_decisions_observations@1` `APPEND_REVISIONS`
- Source: `main.decisions`, 9 columns, `decision_id` only key
- Materialized: `decision_id`, nullable `ts` (`TIMESTAMPTZ`), `run_id`, `decision_type`, `proposal_id`, `strategy`, `underlying`, nullable `expiry` (`DATE`), opaque `payload` (`VARCHAR` from retained JSON-cast text)
- SQL `NULL` stays distinct from JSON `null` text
- Per-revision `decision_id` uniqueness plus ordinal; no invented natural key
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- SQL scalar/record/aggregate byte preflight before transfer
- Retained decision is not native admission, decision replay, or execution permission
- No payload interpretation, admission, or positive decision eligibility
