# Two-track candidate: stabilization fixes and S2 regression coverage

Status: supplied candidate only. Not applied to the user's checkout. Python syntax checked only.
No pytest, DuckDB, mypy, lint, Quack, native recording, Bronze replay or paper validation performed.

Source baseline: inspected remote feat/medallion-feature-store tip
92716f07e1c4e4dfb70c25a56d68735fc009e53f, and Project Files excerpts.
Remote revision is NOT a claim about local HEAD. The acceptance/fixture fixes
are guarded against changed source; S2 APIs must still be checked locally.

## Apply locally

1. Record `git rev-parse HEAD` and `git status --short`.
2. Extract into a temporary directory; review every file.
3. From repository root run `uv run python <extracted-directory>/apply_stabilization.py`.
4. Copy the three new test files to their matching tests/ paths; do not overwrite
   an existing file with the same name without review.
5. Review `git diff` and run the commands below.

```
uv run python -m pytest -o addopts= -q tests/data_platform/test_underlying_assertion_snapshot.py tests/data_platform/test_native_authority_evidence_completeness_report_acceptance.py tests/data_platform/test_authority_acceptance_envelope_regression.py
uv run python -m pytest -o addopts= -q tests/analytics/test_s2_surface_contract_regressions.py tests/market_data/test_s2_vix_provenance_regressions.py
```

Run the project's normal lint/type checks on the changed files afterward.
Keep the Quack opt-in test separate; this bundle does not modify its implementation.
Do not commit logs containing credentials or readiness tokens.

## What this changes

- Fixture CREATE SCHEMA uses catalog.schema while retaining the collision case.
- Acceptance returns the already-computed accepted dictionary, not True.
- New regression binds the acceptance fingerprint to the returned envelope.
- S2 tests exercise total-variance interpolation, no extrapolation, RR25 sign,
  missing forward/wing rejection, freshness, VIX units, raw/reference hash binding,
  instrument mismatch and observational controls using synthetic fixtures only.

## Not completed by this bundle

This is not complete Stage 1/S2. Remaining work requires the actual local source
and database integration tests: durable rejected-observation archival; pinned
Bronze plus retained forward/rate/calendar byte recording; exact read-only replay;
conflict and audited-variant semantics; atomic rollback/orphan/final-audit tests;
expiry capture integration; EOD history/source-switch provenance; paper validation.
Do not treat hypothetical spot/vol stress surfaces as constant-maturity surface evidence.
Do not apply earlier candidate ZIPs without source comparison.
No runner rewiring, live authorization, eligibility promotion or stage advancement.
