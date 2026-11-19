# Explicit research-only quote-bundle publication @1

## Scope and intent
publish_research_quote_bundle(bronze, frame_silver, reference_silver, assessments,
    gold, staging, publications, bundle_id=..., artifact_root=Path(...),
    expected_stage_evidence_fingerprint=..., purpose="RESEARCH_ONLY",
    actor_id=..., code_revision=..., allow_publication=True, initialize=False)

Six owned read-only inputs, separate single-owner file-backed registry, no outer
transactions. This writer supports RESEARCH_ONLY and nothing else. Caller must
explicitly acknowledge publication and supply the reviewed exact stage-evidence
fingerprint. These are local intent gates, NOT authentication, ACLs, signatures
or proof of organizational authority. Use trusted execution ownership/access controls.
Default acknowledgement is False. No decision publication or backdating input.

## Reviewed evidence, not recovery clearance
The native stage consumer is called twice. Exact reader version, target bundle,
active head, completed stage attempts, verified_current status and reviewed evidence
fingerprint must agree. Its nested bundle is encoded without modification; both
verification results must match. RecoveryPlan.NO_TARGET_FINDINGS is never consulted
or treated as authorization. A changed fingerprint requires new explicit review,
even when prices/bundle bytes happen to remain identical.

These reads are sequential, not an atomic cross-database snapshot or publication
barrier. Source changes after the final validation remain possible. Research-only
scope and false decision eligibility are mandatory; this API is not temporal
admission for trades or point-in-time decision data.

## Immutable publication envelope
Registry schema version 1:
- gold.quote_publication_schema_versions
- gold.quote_bundle_publications: publication ID in build_id, versions/purpose,
  exact bundle pin/root/membership, bounded full manifest BLOB and byte count,
  original stage-evidence pin, clock semantics, event/publication/validity metadata
  and first job. Gold contract uses VERSIONED_BUILDS.
- gold.quote_publication_attempts: each job, publication ID, approved and verified
  stage fingerprints and recording time.

Publication ID = SHA256(canonical([[publication version,policy version],bundle ID,purpose])).
feature_version=research-quote-publication@1; policy=research-only-publication-policy@1.
Each registry purpose/version permits one content-addressed publication for the
bundle. Exact retry preserves the original timestamp/content/first approval and
adds its own reviewed attempt; it is NOT a new historical release. Newly reviewed
stage audit evidence can differ on a retry without rewriting original provenance.
All previous linked attempts are bounded/validated; incomplete or entirely failed
publication history requires separate review, never automatic completion.

## What the clock does and does not mean
published_at is the known UTC application publication-RECORD creation clock, sampled
inside the domain transaction for the first record. CLOCK_SEMANTICS explicitly says
PLATFORM_RECORD_CLOCK_NOT_PROVIDER_OR_ECONOMIC_VALIDITY. It is not an exact DB commit,
external availability time, provider publication time, original receipt time,
economic interval or point-in-time admission proof. Full publication authority also
requires completed audit lifecycle; raw rows with timestamps grant no authority.
Later audit-success visibility must not be backdated to this record clock.
No timestamp parameter permits callers to choose historical publication times.

Original staged manifest bytes/ID and false staging flags remain UNCHANGED. They
describe the creation-stage snapshot, not a global claim that no publication record
can ever reference it. The external publication envelope is the new research-only
relationship. Neither Gold nor stage rows/manifests are updated. Economic interval
endpoints and bundle event_ts stay NULL. Historical-validity and decision-eligibility
assertions remain False. Never use this research publication as a trading bundle.

## Commit/lifecycle and failures
Audit PLANNED -> RUNNING -> STAGED -> VALIDATED; two source validations precede
registry mutation. The exact manifest snapshot, first publication record and attempt
link commit atomically in ONE registry transaction. PUBLISHED audit is emitted only
after that domain commit, then SUCCEEDED via the existing ledger context manager.
No filesystem artifact writes are needed: published snapshot bytes live in registry.

Audit transitions and registry commit are not atomic together. If domain insert/
attempt insertion fails, both roll back; no PUBLISHED event is emitted. If a final
publication/success audit write fails, real rows/links remain but the operation
raises. Subsequent normal execution refuses incomplete or no-success publication
history. It does not repair, force success or discard evidence. No PUBLISHED event
is synthesized merely to unblock a staged or recovery record.
A future verified publication consumer must validate content/policy/attempts and
lifecycle before exposing a trusted research snapshot. Do not consume raw rows.
No latest pointer, overwrite, automatic supersession selection or retraction API.

## Boundaries and limits
Exact byte comparisons and maximum codec bundle size (4 MiB), at most 1000 prior
linked attempts, fixed supported versions and purpose. Owned object SQL is fully
quoted catalog.schema.object, including escaped/ambiguous catalog names. Registry
must be separate from ALL inputs/attached paths and outside artifact root; other
Gold/legacy data stores are not publication registries. Default DB creation requires
explicit initialization. No dependency, schema or legacy-workspace compatibility
adapter is added to upstream stores.

## CLI
Default plan opens/creates no databases, directories or artifacts and does no
network/credential lookup. RESEARCH_ONLY purpose and exact bundle/review fingerprint
are required in the plan. Execution needs BOTH --execute AND --allow-publication,
nonempty actor/code revision, existing inputs and --initialize for a new registry.
No --published-at, decision purpose, --repair, --adopt or recovery-plan override.
Failures expose only RESEARCH_PUBLICATION_FAILED. Exit 0 after execution means this
local operation completed, not that a future consumer/admission gate approved it.

## Remaining completion gates
Verified research-publication consumption, retrospective invalidation vs historical
snapshot semantics, temporal/knowledge admission, native decisions and exact replay
are separate work. This snapshot is not all upstream raw/code/config evidence for
complete replay. Data loading/migration remains deferred until platform acceptance.
