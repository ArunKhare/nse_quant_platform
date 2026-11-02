# Audited first-write research-IV stage binding

## Baseline and selected bounded contract

User reports 5d4a33f at local HEAD with QA/tests passed. Supplied origin remains
64ec9b6; push of 5d4a33f is NOT claimed. This accepts the materializer as the latest
user-reported baseline. The new package remains an uncommitted candidate. Direct
repository writes are unavailable; no stage/commit/push is performed by delivery.

Actual updated materializer, file API, codec, current revalidation, archive/audit/
contract patterns and real fixture interfaces were inspected. Existing modules and
inspection repairs are not replaced. Eight additive payloads are supplied; stop
and reconcile if any destination already exists. Preserve local unrelated changes.

This package adds a DISTINCT research-only first-write binding contract:
research-iv-first-stage-record@1 / audited-research-iv-first-stage@1.

The intentionally bounded profile permits ONE immutable stage binding, ONE linked
origin/attempt, ONE native DatasetContract and at most 16 observed jobs per dedicated
store. All jobs are checked, not just a requested scope or successful linked rows.
Repeated writes, retries, supersession, adoption, repair and recovery are explicitly
UNSUPPORTED and rejected without modifying the original row/clock/origin/attempt.
This does not weaken any existing archive retry/history contract; a future version
must explicitly implement any expanded lifecycle. Do not treat this as generic
multi-stage, global latest-state or publication/admission infrastructure.

## Writer

```python
stage_new_research_iv_artifact(
    bronze, frame_silver, reference_silver, assessments,
    source_gold, archive, bundle_archive, target,
    build_id_pin=reviewed_bundle_archive_record_id,
    expected_archive_fingerprint=reviewed_bundle_archive_fingerprint,
    expected_bundle_id=reviewed_feature_bundle_id,
    expected_revalidation_fingerprint=reviewed_current_observation_fingerprint,
    artifact_root=absolute_dedicated_trusted_root,
    actor_id=explicit_actor, code_revision=explicit_revision,
    initialize=False, initialize_artifacts=False,
)
```

Eight supplied database handles: seven existing materializer inputs plus dedicated
file-backed target. No caller verified/materialized/result DTO is accepted. The
writer invokes ACTUAL materialize_research_iv_artifact with reviewed pins only.
That service invokes actual before/after current revalidation and no-replace file
creation. No numerical kernel or source DTO is recreated by this implementation.

New target initialization is explicit and accepts ONLY a genuinely empty database;
it is not schema adoption/migration. Readers never initialize. Artifact-root
initialization is independently explicit and inherits the existing materializer's
new-root-only behavior. New files only: an artifact produced earlier outside this
stage job cannot be adopted, even with matching bytes/current observations.

The target must have only:

- gold.research_iv_first_stage_schema
- gold.research_iv_first_stages
- gold.research_iv_first_attempts
- the four actual medallion_audit foundation tables

It must not alias any input, including distinct same-file cursors/attached files.
Artifact root cannot equal/contain/be inside any database path, including target;
root entries hardlinked to database files are rejected. Trusted, single-owner
handles/root and no outer/shared writer transaction are required. Filesystem
preflight is not a hostile-writer TOCTOU/security boundary.

## Commit boundaries and failure obligations

1. Check whole retained store/audit state BEFORE creating a new audit job.
2. Plan/run actual AuditLedger job BEFORE native materializer/file creation.
3. Require exact typed native materialization success, unchanged observations,
   reviewed pins and denial flags; reread/hash/decode the exact artifact.
4. Atomically register real DatasetContract and insert binding plus attempt in ONE
   domain transaction. The definition is frozen INSIDE each binding's canonical
   bytes, not a shared independently repairable definition row. Its own first_job
   must match the sole successful audit origin/attempt in the same scope.
5. Complete the actual final audit separately. A row without its original complete
   PLANNED/RUNNING/SUCCEEDED history is never an accepted recording.

Contract: gold.research_iv_first_stages@1, Layer.GOLD,
WritePolicy.VERSIONED_BUILDS, owner native_research_iv_first_stage. Existing enums
and foundation API are used; no replacement ledger or quote-only stage format.

Domain failure rolls back contract/binding/attempt, but already-created file remains
an orphan. Final audit failure can leave domain row/file but reader rejects it.
Failed, incomplete or UNLINKED successful jobs (including another scope) block the
whole dedicated profile before requested-record filtering. Missing-job audit events
are also rejected, not lost through joins. Later success cannot heal original failure.
No original exception body is recorded by this package or converted to success.

A native review result raises IvFirstStageNativeRejected with the original native
materialization DTO available as .observation; AuditLedger records FAILED. Its full
negative observations are not silently replaced by later good output. They remain
in memory on that exception, NOT durably stored as complete replay evidence.
Other exceptions propagate. No partial accepted return, automatic cleanup of final
artifact, orphan adoption, retry, final-audit repair or whole-file rollback claim.

## Binding and reader semantics

Binding freezes exact four reviewed pins, literal absolute artifact root, exact
artifact name/byte count, research-only definition/denials, and SHA-256 of each
complete before/after native revalidation DTO. Both DTO digests must match. Stage
build_id is SHA-256 of canonical binding JSON, DISTINCT from feature bundle_id or
bundle archive record ID. scope_id binds exact reviewed pins/root under this format.

Compact record <=8 KiB; roots <=2048 characters; artifact <=4 MiB; one retained row,
one attempt/contract, <=16 jobs, each event history read with a seven-row sentinel.
The actual file API retains its 256-entry bound and all native observation bounds.
Digests commit to observations but do not store their complete bytes. This is NOT
complete exact replay or independent mathematical/source authenticity evidence.
No model suitability, acquisition authority, canonical identity or temporal validity
is manufactured from actor names, hashes or successful audit.

```python
read_research_iv_first_stage(
    target, build_id_pin=exact_stage_record_id, artifact_root=exact_recorded_root,
)
```

Reader verifies WHOLE store, original contract/origin/attempt/audit evidence, exact
requested record, exact recorded root and actual artifact codec/hash/size; then
rereads metadata/artifact to detect observed change. It does not initialize or repair.
Status: verified_research_stage_recording. current_source_checked remains FALSE:
this is original stage-recording evidence, NOT current-source consumption/admission.
The writer's stage status is RESEARCH_IV_STAGE_RECORDED_NOT_PUBLISHED.
A later changed source does not rewrite history; a future distinct current-stage
consumer must explicitly revalidate it. No old-good fallback or global latest claim.

File visibility, domain commit and final audit remain separate. No cross-resource
atomicity or directory-fsync/crash-durability guarantee. Privileged SQL, root/file
replacement, whole-store rollback/deletion and adversarial concurrent writers are
outside this single-owner application boundary.

## Application and QA

No pyproject/dependency/tolerance changes. Preserve Python >=3.12, SciPy >=1.14.0,
cryptography >=46.0.0 and actual Ruff/mypy settings. Use the supplied PowerShell
runner scripts/qa/qa_research_iv_first_stage.ps1 with -ExpectedHead set to the FULL
reviewed local 40-character hash from git rev-parse HEAD, after inspecting actual
branch/status/diff. It is NOT short 5d4a33f, a filename or archive/ZIP checksum.
Runner checks branch/HEAD/ancestry, payload hashes and uv's actual interpreter and
dependency versions, runs focused tests and ALL mandatory commands:

```powershell
uv run pytest tests/data_platform -q
uv run pytest tests -q
uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
uv run mypy
git diff --check
```

It additionally lints the new ZIP verifier and checks untracked payload whitespace.
No dependency replica, stage/commit/push, unrelated-log discard or source repair.
The standalone Python ZIP verifier takes an archive path plus --sha256 (64-char
ZIP checksum), NOT ExpectedHead. Payload manifest excludes itself; full archive
checksum covers the complete ZIP including manifest. Integrity relative to the
supplied pin is not authenticated publisher authority.

## Remaining gates

See separate verification report for tests actually run. Repository native cases
reuse real audit/archive/Gold/model/materializer fixtures with LOWER SOURCE KERNEL
SUBSTITUTED; not full acquisition-to-stage E2E. Existing in-memory fixture handles
remain as designed; no unreviewed read-only file conversion or inspection override.

This is first-write local audited recording, not a complete staging lifecycle,
current-stage consumption, eligible admission, production publication, audited
decision loop, exact replay or operational acceptance. No acquisition, user data
loading/migration/backfill, real identity/key/policy/authority registration, trading,
production publication or cutover is executed. All these holds remain unchanged.
