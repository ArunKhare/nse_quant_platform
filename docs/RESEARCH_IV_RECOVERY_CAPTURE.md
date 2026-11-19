# Audited immutable research-IV recovery observation capture

## Baseline and source reconciliation

Latest accepted baseline: d23b926, user-reported QA-passed, committed and pushed on
feat/medallion-feature-store. No newer failure/commit was reported. Updated actual
research_iv_recovery_plan.py and its boundary tests became retrievable and were
inspected. The code has real formatting changes from the earlier generated delivery;
none is replaced. Historical c73def6/unconfirmed wording in older delivery documents
is not the current acceptance status. Repository access is unavailable; local HEAD,
branch and QA are not independently reproduced.

This package is additive. It depends on the actual @1 reconciliation service and
existing AuditLedger/DatasetContract APIs, not a transitional adapter or quote-only
format. It does not modify the accepted stage writer, reader, consumer, inventory,
reconciliation implementation or existing fixtures. No dependency settings change.

## Why a durable observation rather than recovery execution

The reconciliation service currently returns an in-memory result. This package adds
one immutable, audited retained observation in a separate dedicated file-backed DB.
It retains complete canonical plan DTO bytes, not just their SHA-256. This includes
review_required plans when the same explicitly reviewed plan is reproduced twice.
A failed native call, changed reviewed plan or unstable pair produces no record.
A retained negative is a successful capture of a review outcome, NOT a successful
recovery or positive current-stage observation.

The retained plan itself contains only digests of its internal four observations.
This capture does NOT retroactively retain those stage/inventory DTO bytes, establish
full original replay, or prove the meaning of a self-hash. No current-source pricing
is performed. Actual original stage/audit/artifact checks remain the native plan
service's responsibility. No caller result/verified DTO is accepted by the writer.

## APIs and versions

- research-iv-recovery-capture-record@1: strict canonical nested plan codec.
- audited-research-iv-recovery-capture@1: native writer and original recording reader.

```python
capture_research_iv_recovery(
    staging, target,
    stage_build_id_pin=reviewed_stage_binding_id,
    expected_stage_fingerprint=reviewed_stage_recording_fingerprint,
    expected_plan_fingerprint=reviewed_recovery_plan_evidence_fingerprint,
    artifact_root=recorded_absolute_root,
    actor_id=internal_actor_label,
    code_revision=reviewed_code_revision,
    initialize=False,
)

read_research_iv_recovery_capture(target, build_id_pin=reviewed_capture_build_id)
```

The caller explicitly reviews all three pins. No latest lookup or fingerprint
refresh occurs. The artifact root is checked by actual stage/plan APIs and must not
overlap or contain hardlinks to either DB. Staging and target must be physically
distinct, including cursor/attached/hardlink aliases. Handles are caller-owned.
Use read-only staging and dedicated writable target; do not share writer handles or
wrap calls in external transactions. Target initialization is explicit and only for
a new empty file-backed DB. It does not create the artifact root or adopt old data.

The writer creates PLANNED/RUNNING audit evidence BEFORE invoking the actual native
plan service twice. Complete canonical plan bytes must match each other and the
reviewed evidence fingerprint. Contract and immutable capture/origin linkage commit
atomically in the target. Final SUCCEEDED audit is separate. If final audit fails,
the row can remain visible but is unusable to the reader. No file/domain/audit global
atomicity, repair, later-success healing or crash/rollback protection is claimed.

One capture per dedicated target; no retry, append, supersession or recovery API.
A repeated call checks the original obligations and rejects without replacing its
row, timestamp or job. Any failed/incomplete/unlinked job anywhere in this store
blocks subsequent use, including other scopes and events lacking a job. Native
exceptions durably mark the attempt FAILED through the existing ledger; complete
exception/negative partial DTOs are not retained. Never log arbitrary exception bodies.

The reader checks the whole original contract, canonical bytes, binding hash,
origin/job/events, schema and recording clocks. It does NOT open the artifact root,
reread staging, inventory or current native sources. Its fixed status is
recorded_recovery_observation_not_execution_authorization. A nested positive or
negative plan remains visible as originally recorded, even if artifacts later change.
The reader's evidence fingerprint changes when recording/audit metadata changes;
callers must review/pin it themselves, never treat build ID alone as a full audit pin.

## Bounds and denial semantics

- One immutable record and one dataset contract; at most 16 observed jobs/64 events.
- Record <=270336 UTF-8 bytes; nested plan <=262144 bytes, at most 256 entries.
- Strict exact field sets, canonical bytes, duplicate-key rejection, sorted unique
  name digests, exact supported statuses/reason codes and strict boolean denials.
- Existing native artifact/inventory/kernel bounds remain unchanged.
- Two native plan calls each run two two-pass inventories: up to eight inventory
  passes, 128 MiB aggregate inventory body reads plus original stage reader reads.
  Bounds are not a process-memory ceiling or a global database/filesystem snapshot.

No deletion, adoption, orphan determination, retry, recovery execution, namespace
identity, availability/economic validity, publication, decision eligibility, trading,
user-data loading or migration is added. Actor labels/code revisions in audit do not
authenticate people, authority or governance. Trusted single-owner DB/root conditions
remain; privileged SQL or whole-file rollback can rewrite/delete evidence.

## Verification and local application

Sandbox executed: 25 pure codec tests and 4 actual DuckDB synthetic-SQL rejection
checks. These are NOT native integration, acquisition E2E or actual repository QA.
No successful native computations were mocked, no native dependency replicas were
created. Eleven actual-native boundary tests are supplied for repository QA, using
the existing lower source substitution unchanged. They were NOT run in the sandbox.
Ruff/mypy and all mandatory repository commands were NOT run here.

Payload parsing, trailing whitespace, ZIP CRC, exact unique member set, each payload
SHA-256 and separate archive SHA-256 are independently checked for delivery.
The manifest excludes itself; the archive checksum includes the manifest.

Verify the ZIP using the standalone verifier with ZIP path and --sha256 equal to
the separate 64-character archive digest. Extract into a disposable folder. Review
all additions against local sources. Copy only where destinations do not exist;
reconcile collisions instead of overwriting committed fixes. No auto-installation,
git staging, log cleanup, commit or push is performed.

Run scripts/inspect/qa_research_iv_recovery_capture.ps1 from the repository.
ExpectedHead is the FULL explicitly reviewed 40-character LOCAL git rev-parse HEAD,
not d23b926, a stage pin, filename or archive digest. The runner checks branch/HEAD,
prints the actual uv interpreter, runs all five mandatory QA commands, lints the
standalone verifier and checks delivered/untracked text whitespace. It never stages
unrelated files or discards logs. Passing this package does not satisfy full-platform
acceptance or release the data-loading hold.
