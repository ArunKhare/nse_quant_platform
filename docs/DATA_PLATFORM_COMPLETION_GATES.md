# Native data-platform completion and migration hold

This is an acceptance checklist, not a claim of completion. Actual committed
sources and QA results remain authoritative; user-provided Git markers are not
independent checkout verification.

## Current boundary
Native Bronze/Silver acquisition, normalization, reference evidence, association,
audited persistence and invalidation-aware consumption have reported milestones.
This package introduces versioned in-memory exact price feature candidates.
It does NOT complete Gold persistence, publication, decisions or replay.
No user historical data is loaded or migrated by this package.

## Gates before production data loading/migration
- [ ] Durable native Gold build storage: dedicated DB, contracts, versioned
      definitions/config, pinned inputs, append-only build/attempt evidence,
      exact retries, retained rejections and rollback/final-audit-failure tests.
- [ ] Verified Gold consumers: build/definition/input identity, audit and
      invalidation checks; no old-good fallback or hidden current/latest selection.
- [ ] Immutable feature bundles: exact build membership and canonical manifests,
      sealing, checksums and explicit audited publication. Staging a manifest or
      committing a build is not publication.
- [ ] Temporal admission: verified knowledge/publication cutoffs and separately
      evidenced economic validity. Unknown timestamps remain unknown; no
      substitute receipt/normalization/expiry/HTTP Date. Unknown eligibility blocks.
- [ ] Native decisions: exact bundle/code/config/policy identities and complete
      acceptance/rejection evidence. No legacy decision-loop cutover by inference.
- [ ] Exact replay: use immutable as-recorded bundle/evidence/config snapshots,
      not current-source lookups that introduce future knowledge. Verify versions,
      checksums and deterministic results; keep retrospective invalidation distinct
      from the original decision's information set.
- [ ] Recovery/inspection: bounded corruption and interrupted-job detection,
      reviewed plans, no automatic reseal/truncation or invented audit success.
- [ ] Cross-layer real-service regression suite executed in the actual repository,
      fault tests, all mandatory pytest/Ruff/mypy/diff checks passing.
- [ ] Reviewed scope/acceptance record explicitly authorizes migration preparation.

## Migration remains held
Only after platform acceptance: inventory the legacy data, preserve exact source
artifacts and historical evidence, prepare a dry-run migration plan and quarantine
unknown/mixed provenance. option_stream mixes observations and calculated
analytics; it must not be relabelled Bronze or treated as untouched IV/Greeks.
Missing receipt/publication/economic-validity times stay unknown. Reconcile
counts/conflicts/revisions, verify outputs and audit rollback/recovery before any
explicitly approved migration execution. Do not extend the legacy-workspace adapter.

## This candidate kernel's limits
Prices are exact decoder-scaled observations plus one explicitly derived
intra-packet high-low range. No currency, canonical contract identity, IV, Greeks,
executable depth, strategy signal or economic/temporal eligibility is asserted.
An event timestamp can be NULL and publication remains NULL. These outputs are
candidates, not published Gold datasets or decision-ready bundles.
