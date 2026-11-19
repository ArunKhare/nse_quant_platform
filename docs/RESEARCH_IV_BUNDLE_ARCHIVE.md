# Research-IV bundle archive candidate

## Acceptance status and application

This is an additive candidate patch, not a committed or accepted platform release.
There was no direct access to C:\Projects\nse_quant_platform. Uploaded sources are
snapshots, not proof of HEAD, branch or successful local QA. The last explicit
user-confirmed baseline is 33e5484 on feat/medallion-feature-store. Presence of the
prior bundle candidates in the updated snapshot is confirmed; their local QA and
commit status are still unconfirmed. No new failure was reported or invented.

Review the eight additions before copying them. Do not overwrite an existing path:
if any path already exists, compare it against current local/committed contents
and reconcile deliberately. The archive does not contain replacements for earlier
modules, pyproject.toml, dependency locks, __init__ files, or strategy fixes.
No automatic installer, git staging, commit, push, or data-loading command is supplied.

## Implemented slice

- `research-iv-bundle-archive-record@1`: canonical reviewed requests, full returned
  assembly observations and content-addressed archive identities.
- `audited-research-iv-bundles@1`: explicit initialization, fresh native assembly on
  every write attempt, atomic contract/definition/build/attempt transaction, and
  separate native audit completion.
- Read-only archive verification of full requested scope and shared definition
  origin scope before head classification. It never initializes a missing store.

This is dedicated immutable research-result persistence. It does not complete an
independently reviewed staging lifecycle, stage admission, production publication,
current-source archived-bundle consumption, decisions, or replay.

## APIs

```python
persist_research_iv_bundle(
    bronze, frame_silver, reference_silver, assessments,
    source_gold, archive, target,
    requests=tuple_of_IvBundleRequest,
    actor_id=explicit_actor_id,
    code_revision=explicit_revision,
    initialize=False,
)
read_research_iv_bundle_archive(target, build_id_pin=exact_archive_record_build_id)
```

The writer accepts reviewed build/archive pins only. It does not accept a caller
assembly or a caller "verified bundle" DTO. It invokes the actual existing
`assemble_native_research_iv_bundle` rather than implementing another price kernel.
The returned `build_id` is an ARCHIVE RECORD ID, distinct from the feature artifact's
`bundle_id`. The archive `input_id` hashes the exact sorted reviewed requests and
archive definition. Changing reviewed archive fingerprints changes the input scope;
this is deliberately not a stable authoritative instrument or lifecycle identity.
There is no API that automatically selects a new reviewed fingerprint or latest scope.

The complete result JSON freezes both passes, including all returned negative
observations, and the nested bundle manifest with exact terms/calculation strings.
Both successful assembly and `review_required` are retained. Exceptions are audited
as failures, not converted to partial success. No raw exception body is persisted.

## Dedicated output and transactions

The target must be file-backed and have only these domain tables plus native audit
foundation objects. It must be separate from all SIX input databases, including
attached/same-file aliases and a distinct cursor on the same live file.

- gold.research_iv_bundle_schema_versions
- gold.research_iv_bundle_definitions
- gold.research_iv_bundle_builds
- gold.research_iv_bundle_attempts
- medallion_audit.schema_versions / dataset_contracts / jobs / job_events

The real DatasetContract uses Layer.GOLD and WritePolicy.VERSIONED_BUILDS under
`gold.research_iv_bundle_builds`, version 1, owner native_research_iv_bundle_archive.
All SQL introduced by this package qualifies catalog, schema and object separately.
Existing AuditLedger remains the actual foundation API, not a replacement ledger.
Initialization is explicit, not a reader side effect. It is not a schema migration
or adoption tool for arbitrary partially populated databases.

A planned/running native job precedes assembly. Contract registration, shared
definition origin, immutable result row and attempt link commit together. Final
SUCCEEDED transition is separate. A domain row with failed/incomplete origin does
not constitute a successful recording and later retries cannot repair its origin.

Exact retries retain original ordinal, prior links, clock and first_job_id; only a
new attempt link/audit job is added. Retrying an older result does not promote it
above a later recorded result. The reader verifies all retained rows, attempts and
scoped jobs, including unlinked and failed/incomplete jobs, BEFORE checking the
requested head. Shared definition origin is checked in ITS OWN request scope.
Fingerprints include definition/contract/origin-scope and requested-scope history.
A later exact retry changes observed history fingerprint, even without a new result.

## Bounds and fail-closed behavior

- 1..64 unique sorted reviewed requests; request JSON <=16 KiB.
- Full assembly JSON <=24 MiB; each pass <=8 MiB plus bounded list punctuation.
- At most 256 records and 1000 jobs/attempts per exact request scope.
- All-prior links <=32 KiB; definition/contract materialization <=32 KiB each.
- Aggregate retained request/result/link bytes <=64 MiB per scope, checked by SQL
  before payload fetch; the prospective write is checked against the same limit.
- Audit events are fetched with a seven-row sentinel; only the exact native
  PLANNED/RUNNING/SUCCEEDED sequence is accepted, except the writer's active job.

Bounds fail closed; there is no prefix salvage, status-filtered fallback, pruning,
rounding, tolerance relaxation or repair. Canonical JSON rejects duplicate keys,
nonfinite values, unknown outer fields and noncanonical/trailing bytes. Positive
records validate the actual bundle codec, request/member projection, whole-pass
stability and assembly/revalidation content hashes. These are offline consistency
checks, NOT independent numerical proof or authentication of stored evidence.

`verified_archived_head` describes a fully checked recording at the retained head.
Inspect `recorded_result_status` separately: it can still be `review_required`.
An old requested pin returns `review_required` only after its whole scope verifies.
Broken histories can raise IvBundleArchiveReviewRequired, ValueError or a database
error; callers must treat ANY exception as no usable observation, never use a cache
or older good result as fallback. No "eligible" positive status exists.

## Dependency reconciliation and local QA

The implementation gates native assembly @1 and bundle codec @1. Assembly itself
checks current-source revalidation @1 and audited IV builds @1. Uploaded pyproject
requires Python >=3.12, scipy>=1.14.0, cryptography>=46.0.0; it is unchanged.
The reported uv Python 3.14.2 is not independently verified by this package.

The PowerShell runner requires an explicitly reviewed FULL local HEAD hash. Obtain
it with `git rev-parse HEAD`, inspect `git status --short` and the actual diff, and
supply that hash, not an inferred newer commit. Example from repository root:

```powershell
powershell -NoProfile -File scripts/qa/qa_research_iv_bundle_archive.ps1 `
  -ExpectedHead <reviewed-full-40-character-head>
```

The runner verifies branch/HEAD and payload hashes, prints the interpreter uv
actually executes, verifies project dependency bounds/installed versions, runs the
previous unconfirmed bundle tests FIRST, then the new tests and all mandatory QA:

```powershell
uv run pytest tests/data_platform -q
uv run pytest tests -q
uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
uv run mypy
git diff --check
```

It additionally checks added/untracked payload whitespace. It does not change
source, install alternate dependency replicas, stage files or discard logs. A
nonzero command stops the runner. Its final message can only be produced locally
by actually running it successfully. The runner itself was NOT executed here.

## Verification and remaining boundaries

See the separate verification document for executed versus unexecuted checks.
Repository boundary tests reuse actual assembly/archive/revalidation/model/Gold SQL
fixtures with the LOWER SOURCE KERNEL SUBSTITUTED. They are not full native E2E.
No successful numerical native computation was mocked to produce delivery results.

All output remains research only. No receipt, audit event, actor name, provider
label, stored hash or offline signature grants source authenticity, canonical
identity, model suitability, common economic time, availability, historical
validity, governance authority or decision eligibility. Source event times retain
individual unknown values. Generic event_ts/published_at remain NULL. Repeated
observations do not establish a cross-database atomic snapshot.

No live acquisition, user-data migration/backfill/loading, real identity/key/policy
registration, production publication, trading or cutover was executed. These holds
remain in force. Passing this candidate's QA is not whole-platform acceptance.
