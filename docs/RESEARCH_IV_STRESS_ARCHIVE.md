# Audited immutable native spot-stress observation archive

## Accepted baseline and inspected interfaces

Latest accepted user-reported baseline: daf62e1, with HEAD/origin aligned and all
QA/tests passed. d64376f is the accepted native fixed-IV spot-stress milestone.
No newer failure/commit was supplied. Current formatted native stress/numerical/CLI
sources and boundary fixture interfaces were retrieved. Existing recovery recording,
IV archive/record and ledger/contract APIs were used as inspected storage patterns.
No existing source, formatting fix, fixture assertion or dependency is replaced.
Repository access is unavailable; local branch/full HEAD/QA are not independently
reproduced. Historical unexecuted-sandbox statements do not revoke user acceptance.

## Purpose

The accepted native stress service returns an in-memory complete observation; the
CLI exposes only a bounded projection. This package durably retains the COMPLETE
native DTO, original three reviewed pins, exact shock tuple and frozen definition.
Both positive and review_required outcomes are recorded, including before/after
native observations and provisional/repeated studies exactly as returned.
A successful recording of a review is NOT acceptance of a stress study.

This is an original research observation archive, NOT publication, staging, native
current revalidation, a recovery permission, model suitability or decision admission.
It does not connect to the transitional adapter or extend a quote-only format.

## APIs

- research-iv-spot-stress-archive-record@1: strict canonical retained envelope.
- audited-research-iv-spot-stress-recording@1: native writer and original reader.

```python
persist_research_iv_spot_stress(
    bronze, frame_silver, reference_silver, assessments, source_gold, archive, target,
    build_id_pin=reviewed_underlying_iv_build,
    expected_archive_fingerprint=reviewed_iv_archive_fingerprint,
    expected_revalidation_fingerprint=reviewed_native_iv_fingerprint,
    shocks_bps=(-1000, 0, 1000),
    actor_id=internal_actor_label,
    code_revision=reviewed_revision_label,
    initialize=False,
)

read_research_iv_spot_stress_archive(target, build_id_pin=reviewed_stress_record_id)
```

Seven caller-owned handles. Use read-only source/member archive handles and a new
physically separate dedicated file-backed target for recording. Target must differ
from all six inputs, including distinct cursors, attached-file paths and hardlinks.
Memory source paths remain legitimately absent, not invented. Original native input
alias protections remain. No caller result/study/IV/spot/terms DTO is accepted.
No latest lookup, replacement pins or native fingerprint refresh occurs.

The writer validates the request before initialization/audit. Initialization is
explicit and ONLY for a genuinely empty new target. No missing directory is created,
old data adopted or existing store repaired. Do not wrap calls in external/shared
transactions. Trusted single-owner connection/filesystem conditions remain required.

## Recording transaction and audit

1. Validate exact reviewed pins/grid, dependency profile, actor/revision labels and
   physically separate target. Check the WHOLE dedicated store before new work.
2. Persist PLANNED/RUNNING audit evidence BEFORE the actual native service call.
3. Invoke the ACTUAL native stress service ONCE. That service already performs
   revalidation -> grid -> revalidation -> repeated grid for accepted observations.
   A negative before/after observation is retained, not discarded or promoted.
4. Require the exact native result type, version, request scope, supported status,
   explicit research denials and bounded complete canonical envelope.
5. Atomically commit the dataset contract and immutable recording/origin link in
   the target domain transaction. The origin/attempt link is the row's first_job_id;
   this no-retry profile has no separate retry-attempt history or shared definition.
6. Complete final audit separately, then invoke actual original-recording verification.

One recording per dedicated store, ONE linked original job/attempt and contract.
No retries, append, supersession, adoption, repair or recovery. Repeated writes reject
without changing the original row/clock/origin. Any failed/incomplete/unlinked job
ANYWHERE in this target blocks use, including other scopes and orphan events.
No later-success healing. Jobs/events are checked before head/result interpretation.

Native/kernel/codec/SQL exceptions propagate. A failed native call leaves no complete
result row; existing AuditLedger records FAILED where possible. Arbitrary exception
bodies are not stored in audit. An exception before complete native return is not
fabricated into a retained review DTO. Final-audit failure can leave a visible row
but the reader rejects it. Domain, source observations and final audit are NOT one
atomic resource transaction. No crash/rollback/privileged-SQL protection is asserted.

## Retained bytes and identities

Envelope freezes version/definition, exact request and full result AS AN OBJECT,
not just scalar IV, a CLI projection, source hashes or rounded model values.
Stress recording build_id = SHA-256(canonical complete envelope).
It differs from the underlying IV build ID, numerical study fingerprint and native
stress evidence fingerprint. Scope binds the exact request and definition. The
reader's evidence fingerprint additionally binds original metadata/audit clocks.
Callers must review that full fingerprint where current/audit pinning is needed;
record ID alone is not a pin of mutable recording metadata.

All original individual source clocks remain inside the complete native DTO, including
None. Generic event_ts/published_at and canonical_contract_id remain None.

The offline codec checks exact envelope/native/study field sets, canonical bytes,
duplicate/nonfinite JSON, request linkage, boolean denials, grid/size/shape constraints,
study fingerprint consistency and positive/review exposure rules. It checks complete
native before/after payload BOUNDS and preserves them as nested JSON; it does NOT
independently rerun/validate every inner archive/Gold/revalidation schema or BSM price.
Only the writer obtains those bytes from the ACTUAL native service. An offline
self-consistent envelope supplied by an untrusted party is NOT proof of native truth.

## Reader semantics

Fixed status: recorded_research_iv_spot_stress_not_published.
recorded_native_status separately preserves positive or review_required.
original_recording_checked=True means original whole-store contract/origin/audit/
canonical-byte obligations were checked. current_source_checked=False and
model_computation_rechecked=False ALWAYS. The reader performs NO source handles,
artifact access, numerical/model computation, initialization, repair or writes.
It may verify a historical recorded result even when original source data later
becomes blocked. Retained nested current_source_checked flags describe that ORIGINAL
observation, not the reader's current validity. Never relabel this as fresh pricing,
complete historical replay, trusted governance or publication eligibility.

## Bounds

- One domain record/contract; <=16 observed jobs and <=64 observed events.
- Complete record <=24 MiB (25165824 bytes).
- Each nested complete native per-build observation <=8 MiB.
- Each retained stress study <=64 KiB; 1..16 exact shock values, unchanged -5000..5000.
- Frozen definition inside each envelope; no repairable shared definition row.
- Canonical JSON/hash/SQL copies add overhead. These are PAYLOAD bounds, NOT a total
  process-memory guarantee. Existing source/kernel/archive bounds stay unchanged.

No model repricing is done by the reader; no new numerical tolerances, clipping,
solver substitutions or dependency downgrades are introduced. Fixed-IV hypothetical
changes remain model price changes, not portfolio P&L or observed market responses.
All authority/identity/suitability/availability/historical/publication/eligibility
claims remain false/None. Actor/revision labels do not authenticate humans or roles.

## Tests and verification limits

Sandbox runs pure record/request codec cases and actual disposable DuckDB synthetic
schema rejection checks. These do not establish native computations or full repository
QA. No dependency replica or fabricated successful-native harness is used. Positive
native/study roundtrip is exercised by supplied repository integration tests using
actual source/model/ledger APIs and the original lower source substitute unchanged.
Ten native boundary tests are supplied but NOT run here. They cover native invocation
after RUNNING audit, exact complete DTO retention, negative before/after outcomes,
no retry, failed original obligations, final-audit separation, original-only reads,
read-only reopening/clock fingerprints, orphan events and physical target aliases.
Ruff/mypy, mandatory repository QA, Windows runner and full native E2E are NOT run.
See delivery verification report for exact executed counts and checksum results.

## Apply and QA

Use standalone verifier with ZIP path and --sha256 equal to the SEPARATE 64-character
archive checksum. Do not use the script payload hash in MANIFEST or a Git HEAD.
Manifest excludes itself; whole-ZIP checksum includes it. Extract to disposable folder,
review additions and copy only if destinations do not exist. Reconcile collisions;
never overwrite committed fixes. No auto-installer/staging/commit/push or log deletion.

Run scripts/inspect/qa_research_iv_stress_archive.ps1 from the repository with
ExpectedHead = explicitly reviewed FULL 40-character LOCAL git rev-parse HEAD.
It is NOT daf62e1, a filename, native/archive fingerprint or ZIP digest. Runner checks
branch/HEAD, actual uv interpreter and ALL five mandatory commands plus whitespace.
Do not auto-fill an unreviewed HEAD or weaken tests/bounds/dependencies to pass QA.

Real acquisition, user-data loading/migration/backfill, identity/key/policy/authority
registration, production publication, trading and cutover remain prohibited. Synthetic
disposable fixtures only. Package QA is not whole-platform acceptance or data-loading
permission. No actual recording or registrations are executed by this delivery.
