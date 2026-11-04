# Audited migrated-publication admission capture

## Scope and holds

This additive package extends the accepted migrated-price research publication and
admission family with immutable first-write policy-observation capture and explicit
revalidation. It does not add a positive decision lane, strategy execution, orders,
legacy-paper-loop extension, production registration or migration authorization.

Real-data loading/migration, production publication, authority registration, trading
and cutover remain HELD. Disposable synthetic tests are permitted. Research policy
acceptance is neither organizational authorization nor canonical identity/time proof.

## Inspected native integration

The producer calls actual legacy_market_publication_admission.assess_legacy_publication_use
twice. That accepted API calls the actual pinned retained publication reader; caller
successful DTOs, raw offline receipts and fabricated source results are not import APIs.
The new reader replays the exact accepted policy codec and checks original audit links.

Actual native AuditLedger handles execution. The original admission_capture_reader
three-phase lifecycle verifier is reused. Shared publication helpers provide actual
catalog-qualified identifiers, file separation, bounded SQL text and UTC clocks.

The quote-specific admission_capture profile is not modified or populated with a
migrated receipt. Its policy decoder explicitly expects quote-publication content.
A versioned dedicated decision_inputs profile is necessary. Like the inspected
native decision-input capture, its explicit CONTRACT is a tuple, not a medallion
DatasetContract pretending decision_inputs is Bronze, Silver or Gold. The exact
contract/policy definition is retained in the initialized version table and checked
on every read/write. No Gold contract or quote codec is relabeled.

The existing quote capture/revalidation and native refusal consumers remain unchanged.
There is no generic dispatch bridge or assertion that their DTOs accept these captures.

## API surface

legacy_market_admission_capture.py:

- LegacyAdmissionPins(publication_id, recording_fingerprint)
- scope_id(publication_id, request)
- initialize_legacy_admission_capture(empty_file_backed_target)
- capture_legacy_publication_use(readonly_publications, target, pins=..., request=...,
  actor_id=..., code_revision=...)
- read_legacy_admission_capture(readonly_capture, capture_id=...,
  expected_recording_fingerprint=...)

legacy_market_admission_revalidation.py:

- revalidate_legacy_admission_capture(readonly_publications, readonly_captures,
  capture_id=..., expected_recording_fingerprint=...)
- revalidate_legacy_admission_upstream(readonly_bronze, readonly_silver, readonly_gold,
  readonly_publications, readonly_captures, capture_id=...,
  expected_recording_fingerprint=...)

Caller owns connections and closes writer owners before read-only reopen. No outer
transactions or shared writers. Initialization requires an empty dedicated file;
partial initialization cannot be adopted. Actual live-file alias checks reject
same-file cursors without closing the owning connection. Public readers enforce
actual read-only mode. New/modified SQL uses quoted actual catalog.schema.table.

## Captured facts and limitations

Every capture retains exact frozen-summary receipt bytes and all policy results,
publication ID and separately reviewed publication recording fingerprint, canonical
request including separate knowledge_cutoff/economic_at axes, full reasons, native
capture link, audit job and import-record clock. Native capture ID binds scope,
publication recording pin and receipt hash. A separately reviewed recording
fingerprint additionally binds clocks, all materialized metadata and original audit.

This retains the complete accepted admission receipt, NOT another 140-MB publication
manifest or original provider payload. Full publication content remains behind its
explicit source ID/recording pin and actual retained reader. Offline policy receipt
replay proves computation on a summary, not the original source's authenticity.
Native capture verification is a separate original-recording assertion, not an
independent authenticated source/audit root or permission boundary against DB rewrite.

Both ACCEPTED_RESEARCH_ONLY and REJECTED policy results can be valid captures.
POINT_IN_TIME_DECISION stays rejected even when both requested times equal record
clocks. Exact revalidation of that refusal returns matched_rejected_input, not a
positive admission. Research authorization, decision eligibility and replay
authenticity remain false in capture/revalidation DTOs. No strategy/risk/execution
stage is run or claimed. There is no independently_verified override.

## First-write and original obligations

Scope binds this store version, publication ID and normalized request axes. It
excludes reviewed publication recording fingerprint and execution identifiers. A
failed recording pin therefore cannot be healed with the correct pin or new actor.
A genuinely different request is a different scoped observation, not a retry or
reassessment history. There is no history-head/recovery/adoption claim in this @1.

Any prior scoped capture, attempt or audit job blocks another write before source
assessment. Two complete actual policy observations must match exact bytes; status
alone is insufficient. The captured receipt is replayed before persistence. Captured
record plus original attempt link commit atomically. Domain rollback leaves the
failed original audit obligation. The final SUCCEEDED audit is separate: committed
content with failed/missing final audit is unreadable and cannot be adopted.

The reader recomputes every materialized scalar and full policy result, capture ID,
scope, definition/contract, original job/config/lifecycle and exact attempt linkage.
It includes scope/ID/job matches so same-scope extra jobs/orphans cannot hide behind
a good subset. Verification is request-scope-specific, not a whole-database frontier
or whole-platform all-clear. Unrelated requests are not implicitly accepted or scanned.

## Three revalidation levels

1. Retained capture replay checks original capture/audit and frozen policy bytes.
   No current publication or upstream assertion is made.
2. Current publication revalidation brackets two actual fresh policy assessments
   with pinned capture reads and requires full original receipt reproduction. It
   checks the actual retained publication now, NOT current Bronze/Silver/Gold.
3. Current-native revalidation adds two actual revalidate_legacy_research_publication
   calls and brackets those with publication/capture checks. Only this separate
   result sets current_native_upstream_checked=True.

No level reads/asserts current legacy SQL equality. Changed legacy SQL can coexist
with unchanged preserved native evidence. An altered native Bronze original audit
blocks level 3, while levels 1/2 may remain valid. An altered publication original
audit blocks levels 2/3, while a retained capture remains replayable. Corruption or
operational errors raise; they never become business acceptance or a recovered
old-good result. Repeated agreement is not atomic cross-database time coherence.

## Independent resource bounds

- One scoped capture and one original attempt/job are accepted.
- Full receipt: 1..32768 bytes, unchanged accepted policy bound.
- Canonical request <=512 bytes; reason array <=4096 bytes on retained transfer.
- SQL aggregate count/receipt-byte preflight before BLOB transfer, across capture ID
  or scope, plus independent per-cell CASE guards.
- Definition/contract <=32768 bytes; bounded/lazy object inventory and LIMIT overflow
  checks for jobs, attempts and events; CASE-guarded execution identifiers.
- No unbounded scan, partial success, paging, automatic recovery or limit inflation.

All upstream profile/resource/runtime limits remain unchanged. The accepted bundle
materializes multiple JSON/hex copies during source checks; no streaming or small
peak-memory claim is introduced here. Naive request clocks are never assigned UTC.
Capture and audit clocks use UTC-normalized instants and are not market availability.

## Verification attribution

User-confirmed QA through 5cc17a1 is accepted and closed. The supplied Git output
places local HEAD at 5cc17a1 and origin at 483ad7f; no assistant Git inspection,
push, Windows/uv execution or current worktree-clean claim was made.

The new native tests import actual accepted synthetic publication fixtures, which
produce the real legacy -> partition Bronze -> Silver -> Gold -> bundle -> research
publication path before capture, retained replay and both revalidation levels.
Failure injection raises at actual boundaries, rather than supplying successful
lower-source substitutes and labeling them E2E. They cover rejected PIT captures,
full scalar/receipt corruption, original jobs/links/audits, first-write, wrong pins,
final-audit failure, real SQL rollback, second-assessment failure, source distinctions,
SQL bounds, actual catalog/schema collision, timezone normalization and file aliases.
These repository-dependent tests have NOT been assistant-executed.

The small contract suite checks exact pins, request typing/axes and scope normalization.
Assistant isolated checks, if performed, are reported separately in the delivery
response; they are not native producer/reader E2E. Python syntax/line-length/whitespace
and ZIP nonempty/exact members/CRC/payload equality are checked before delivery.
Ruff, mypy, Windows and full repository QA are NOT implied by those checks.

## Applying and verifying new additions

Review/copy absent additions only. Stop/compare if any destination exists. No accepted
module or QA repair, runtime log, scripts/qa, PowerShell runner, payload-hash manifest
or standalone ZIP verifier is replaced or included. Preserve logs/live_status.json.

New-work repository checks:

    uv run python -c "import sys; print(sys.executable); print(sys.version)"
    uv run pytest tests/data_platform/test_legacy_market_admission_capture_contract.py -q
    uv run pytest tests/data_platform/test_legacy_market_admission_capture_native.py -q
    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Also inspect untracked additions for whitespace. These new-work checks do not reopen
closed prior QA. Package QA is not platform acceptance or a real-data release decision.

### Assistant-executed isolated checks for this delivery

Python 3.12.8 / DuckDB 1.2.2 dependency-adapter harness:

- 8 contract cases passed in pytest.
- Initial implementation: actual new DDL/materializer/reader and publication-only
  revalidation roundtrip passed; 21 isolated SQL/filesystem checks passed. They
  exercised scalar/content corruption, independent SQL guards, original recording
  obligations, timezone fingerprints, real domain SQL rollback, no adoption after
  domain/final-audit failure and same-live-file cursor preservation.
- Final source adds explicit independent producer receipt/reason-byte checks.
  Its new-schema capture/reader/publication-revalidation roundtrip passed, and
  oversized observed receipt rejection was independently exercised before transfer.
  The initial 21-check batch was not rerun in full after this small addition.
- Audit, publication-policy/source and native lifecycle/request dependency boundaries
  were adapters, not the actual repository dependency graph. These results are
  NOT native E2E and do not authenticate upstream observations.

Supplied native tests were inventoried, not executed. No independent Windows/uv,
Ruff, mypy, repository/full pytest or Git execution occurred. Archive/syntax checks
were rerun over the final payloads, not inferred from the earlier provisional ZIP.
