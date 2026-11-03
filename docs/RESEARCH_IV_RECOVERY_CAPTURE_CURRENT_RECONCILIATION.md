# Current reconciliation of an exact reviewed research-IV recovery capture

## Baseline and inspected sources

Latest accepted baseline is 831fc82 on feat/medallion-feature-store, user-reported
QA-passed, committed and pushed. No newer commit or failure was supplied. The actual
current capture writer/reader, strict record codec, capture boundary tests, native
recovery plan and pyproject.toml were retrieved and inspected. Historical baseline
and "not sandbox-executed" wording in earlier delivery docs is historical, not a
retraction of the user's acceptance report. Repository access remains unavailable;
local HEAD/branch and QA were not independently reproduced.

This additive package changes no existing module, fixture, dependency or tolerance.
Native audit, artifact, inventory and first-stage contracts remain intact.

## Why this service

The accepted capture reader verifies its original recording even after artifacts
change. This service addresses that explicit gap: it compares the actual current
stage/artifact reconciliation with complete retained plan DTO bytes under an exact
reviewed capture fingerprint. It does not merely rename an archived recording as
current, compare one scalar/evidence hash, or authorize a recovery operation.

## Native API

```python
revalidate_research_iv_recovery_capture(
    staging, capture,
    capture_build_id_pin=reviewed_capture_binding_id,
    expected_capture_fingerprint=reviewed_full_capture_recording_fingerprint,
    artifact_root=exact_recorded_absolute_root,
)
```

Versions:
- research-iv-recovery-capture-observation@1: bounded pure byte comparison.
- research-iv-recovery-capture-current-reconciliation@1: actual native service.

Capture build ID is NOT the stage binding ID, feature bundle ID or plan fingerprint.
The expected capture fingerprint is from the actual original recording reader and
must be explicitly reviewed. No latest lookup or auto-refresh is supported. Caller
supplies no plan DTO, verified result, replacement stage pin or artifact identity.

Use existing caller-owned read-only handles to physically distinct staging/capture
DB files. Same-file cursor, attached path and hardlink aliases are rejected before
native reconciliation. Artifact root cannot redirect, overlap either DB path, or
contain an entry hardlinked to either DB. No connection is opened or initialized;
no SQL data mutation, audit job or filesystem write is requested by this service.
The existing reader uses its own read transaction; no external transaction should
wrap the call. Trusted single-owner handles/root are required.

## Invalidation-first sequence

1. Gate exact dependency versions/bounds and validate both reviewed capture pins.
2. Call the actual original capture reader. Known incomplete original obligations
   return review; unexpected codec/database errors propagate.
3. Require exact reviewed full capture fingerprint and typed complete recording.
4. Decode/verify actual retained bytes and reconstruct frozen stage ID/fingerprint
   from them, never from caller-supplied alternate stage references.
5. A retained review_required plan stops BEFORE stage/root/native work. Even later
   good artifacts cannot upgrade it. This is not a new record or repair path.
6. For retained retain-only plans, require the exact recorded root and physical
   separation, then invoke the ACTUAL native recovery-plan service twice. Each call
   already performs stage -> inventory -> inventory -> stage using real APIs.
7. Validate each complete returned DTO through the actual strict @1 capture codec.
   Compare canonical COMPLETE fresh plan bytes to each other and to the actual
   retained complete plan bytes, not just plan.evidence_fingerprint or entry count.
8. Reread the actual complete original capture/audit recording. Require unchanged
   full DTO, including its evidence fingerprint. Only then expose a positive result.

Both good-bad and bad-good native outcomes are retained in review results. There is
no later-good selection. A known after-read capture audit failure preserves both
native observations and comparison. Unexpected DB/filesystem/codec/native exceptions
propagate without accepted partial output, cache fallback, repair or fingerprint
refresh. Native stage-fingerprint failure also propagates: never substitute a newer
reviewed stage fingerprint to bypass the original capture's frozen inputs.

## Result meanings

Positive: matched_current_research_iv_recovery_capture. Required narrow facts:
- archived_recording_verified
- current_reconciliation_checked
- exact_recorded_plan_reproduced
- capture_unchanged_observed

Only positive exposes plan_evidence_fingerprint and evidence_fingerprint. A review
can retain valid partial facts (including reproduced bytes before an after-audit
failure), but both accepted IDs remain None. Full before/after original capture DTOs
and both complete fresh native plans remain attached when available.

The retained capture includes complete PLAN bytes. Equality is genuine direct
retained-plan-byte comparison. The plan's internal original stage/inventory DTOs
were only represented through digests; this service does not reconstruct those
missing bytes or claim full original observation replay.

current_source_checked remains FALSE even on positive. This service does not invoke
pricing, source-Gold/archived-IV revalidation or current-stage consumption. A pricing
source can change while this reconciliation still matches. For pricing freshness use
the accepted separate current-stage consumer; never infer it from this result.
No cleanup, orphan determination, adoption, retry, recovery execution, authority,
identity, suitability, availability, historical economic validity, publication,
atomic cross-database snapshot or decision eligibility is established. All such
flags remain false/None; event_ts and published_at remain None.

## Bounds

Each native canonical plan <=256 KiB (262144 bytes); three compared payloads total
<=768 KiB, NOT a total process-memory ceiling. Actual capture record <=270336 bytes.
Canonical validated record wrappers and full original DTOs add memory overhead.
Two native plans run eight inventory passes total: <=128 MiB inventory body reads,
plus existing stage-reader reads. Existing 256-entry, 4 MiB artifact and all nested
limits remain untouched. Repeated observations are not a global atomic snapshot or
continued validity promise. Whole-file rollback/deletion/privileged SQL remain out
of scope. No writer/retry/recovery/publication API or new CLI is introduced.

## Tests and verification

Sandbox executed 22 focused tests: 21 pure byte-comparison tests plus a service DTO
and signature/default-denial test. They are NOT native integration. No successful
native/model computations or dependency implementations were mocked or replicated.
Sixteen repository boundary cases are supplied using actual capture/plan/stage/audit/
filesystem APIs with the existing lower source substitute unchanged. They were NOT
executed here; not full native acquisition E2E. Ruff/mypy are unavailable here.
All mandatory actual-repository QA commands and full native E2E remain NOT RUN.

Delivery checks cover Python syntax, payload whitespace/line length, a nonempty ZIP,
CRC, exact unique member set, every payload checksum and separate archive checksum.
The manifest excludes itself; the archive hash includes the manifest. The standalone
verifier is additionally exercised against checksum/member/payload corruption.
Integrity relative to a reviewed checksum does not authenticate an issuer.

## Apply without overwriting current sources

Verify the delivered ZIP using the standalone verifier: ZIP path and --sha256 equal
to the separate 64-character archive hash. Extract into a disposable folder, review
all additions against local HEAD, then copy only where destinations do not exist.
Reconcile any collision; never overwrite accepted fixes with this generated patch.
No auto-installer/staging/commit/push or log cleanup is included.

Run scripts/inspect/qa_research_iv_current_recovery_capture.ps1 from the repository.
ExpectedHead must be the explicitly reviewed FULL 40-character LOCAL git rev-parse
HEAD output, not short 831fc82, a filename, stage/capture fingerprint or ZIP checksum.
Runner checks expected branch/head, prints the actual uv interpreter, runs all five
mandatory QA commands, lints the standalone verifier and checks untracked payload
whitespace. No tests/typing/dependencies/bounds are weakened and no skips added.

All real acquisition/loading/migration/backfill/identity/key/policy registrations,
production publication, trading and decision-loop cutover remain prohibited. Passing
this package is not whole-platform acceptance or release of the data-loading hold.
