# Native research publication of complete return-window analytics

## Scope and versioned profiles

This additive package connects accepted persisted return-window analytics to actual
native research bundle/publication/read/admission paths. It does not relabel window
statistics as provider quotes or legacy geometry, or extend the old paper loop.

- Bundle: legacy-window-research-bundle@1.
- Publication: legacy-window-research-publication@1.
- Purpose policy: legacy-window-research-only-policy@1.
- Command: publish.legacy_window_research_bundle@1.
- DatasetContract: gold.window_research_publications / 1 / VERSIONED_BUILDS.
- Admission: legacy-window-research-admission@1.

QA through a55f491 is accepted/closed as user-confirmed, with matching supplied
HEAD/origin pointers. No assistant full hash, Git/worktree inspection, push, Windows
or uv-selected execution is claimed. Distributed-testing dependency work a919045 and
all accepted modules/QA repairs remain untouched.

Only disposable synthetic publication is released. Real-data loading/migration,
production publication, identity/key/policy/authority registration, trading and native
cutover remain HELD. allow_research_publication=True acknowledges intent; it is not
an ACL, source authenticity proof, proof of synthetic origin or production approval.

## Native integration and compatibility

Actual legacy_return_window_store revalidate_return_window_gold and _recording are
called repeatedly. The complete original context is read with an independent SQL
CASE guard. Offline content replay uses actual _recompute/_id to reproduce the whole
window build, all inputs/outputs, retained source return/geometry content and policy.
No caller-successful source result, offline bundle or forged lower-source receipt is
accepted by the native producer as original recording verification.

The publication profile uses actual native AuditLedger/JobState, DatasetContract,
and existing legacy_market_publication helpers for catalog-qualified identifiers,
source-file separation, bounded text transfer, canonical UTC clock hashing and exact
six-phase publication lifecycle verification. Admission reuses existing AdmissionRequest
and its separate knowledge_cutoff/economic_at canonical codecs.

The existing geometry and quote bundle/publication/admission @1 codecs are intentionally
unchanged: their types and publication identities cannot represent window analytics.
This is a versioned sibling profile of the same native audit/contract/lifecycle pattern,
not insertion of window values into geometry/quote records. Dedicated files/tables
remain profile-owned; there is no generic cross-profile dispatcher or universal registry.
Native decision/refusal consumers and prior geometry admission-capture APIs are NOT
silently widened to accept this new profile. This package does not add a persisted
window-admission capture or strategy/decision/execution lane.

These inspected private source/helper interfaces are dependencies, not a claim of
stable public plugin contracts. Incompatible future source changes require review.

## APIs

legacy_window_bundle.py:

- WindowBundleRequest(build_id, recording_fingerprint): pinned WINDOW build, not the
  ReturnWindowPins that identifies its upstream return build.
- assemble_window_bundle(bronze, silver, geometry, returns, windows, request=...)
- replay_window_bundle(raw, expected_bundle_id=...)
- revalidate_window_bundle(bronze, silver, geometry, returns, windows, raw=...,
  expected_bundle_id=...)

legacy_window_publication.py:

- initialize_window_publication(empty_dedicated_file)
- publish_window_research_bundle(bronze, silver, geometry, returns, windows, target,
  request=..., expected_bundle_id=..., actor_id=..., code_revision=...,
  purpose="RESEARCH_ONLY", allow_research_publication=True)
- read_window_publication(readonly_publications, publication_id=...,
  expected_recording_fingerprint=...)
- revalidate_window_publication(bronze, silver, geometry, returns, windows,
  readonly_publications, publication_id=..., expected_recording_fingerprint=...)

legacy_window_admission.py:

- assess_window_publication_use(readonly_publications, publication_id=...,
  expected_recording_fingerprint=..., request=AdmissionRequest(...))
- encode_window_admission(receipt)
- replay_window_admission(raw, expected_receipt_id=...)

Caller owns connections; close all writer owners before readonly reopen. No outer
transactions/shared writers/implicit reader initialization. Target must be empty,
dedicated and file-backed; partial initialization is not adopted. Actual source readers
and public publication reader enforce readonly mode. Live-file aliases are rejected
without closing parent owners. New SQL/tests quote actual catalog.schema.table names,
including real gold.duckdb/gold-schema collision fixtures.

## Complete content and limitations

One complete window build per bundle/publication, with every full Silver input and
window output, exact source definition, reviewed window recording pin, source return
pins, full nested source context and reviewed window/cadence policy. Return/geometry
intermediates are reconstructed using their actual accepted codecs rather than
serialized again. Every ordinal remains present, including warmup, missing/invalid
or cadence-mismatched UNAVAILABLE rows. No good-subset publication or empty success.

The inner bundle and analytic rows retain publication_asserted=False and null
published_at. Bytes are not rewritten when the OUTER research publication is recorded.
Publication recorded_at and audit success clocks are platform receipt clocks, never
provider availability, independent economic validity or authoritative session clocks.

Window statistics remain exact sum/mean squared SIMPLE returns, not conventional RV,
annualized volatility, sample variance or log-return realized variance. Policy cadence
agreement does not authenticate NSE sessions, source completeness or canonical identity.
False independent availability, economic validity, authoritative market coverage and
decision eligibility, and null canonical identity remain explicit and replayable.
Inherited exact-runtime equality requirements remain; labels are not authenticated
interpreter/build/source-code attestation. No supplied authority/root is invented.

## Native observation versus offline replay

Native assembly performs a full actual current-upstream observation and retained window
recording read, constructs complete bytes, then repeats the entire observation and
requires equality. These actual sources include original audit/link/orphan obligations.
Repeated agreement is not an atomic multi-database snapshot or independent time proof.

Offline replay bounds exact bytes/counts before hex decoding, recomputes all content
and original source build identity, and requires complete canonical-byte equality.
It does NOT authenticate the bundle's recording-fingerprint declaration or original
native source/audit history. Rehashing a well-formed changed declared fingerprint can
pass offline content replay; actual pinned native assembly rejects it. This distinction
is deliberate and tested, not an audit-healing or authenticity mechanism.

Retained publication read verifies original registry/audit and frozen full-bundle
recomputation, without touching current native upstream. Current-native publication
revalidation additionally invokes actual bundle assembly and compares all bytes,
bracketed by pinned publication reads. It returns the unchanged archived DTO, so
current_source_checked remains False; successful invocation supplies the extra check.
Neither API asserts/reads current legacy SQL equality. Changed legacy SQL can coexist
with unchanged retained native evidence; missing original upstream audits block current
checks while archived publication replay can remain valid.

## First-write, transaction and final-audit obligations

Publication scope binds profile and window build ID, excluding source recording pin,
bundle ID/runtime and execution labels. Different window-policy builds have different
source build IDs; changing a pin for the same source cannot heal an original failure.
Existing source/scope records, attempts or audit jobs block writes before source reads.
Successful retry is also deliberately unavailable in this first-write profile.

PLANNED/RUNNING -> actual assembly/review pin -> STAGED -> second actual assembly and
full replay -> VALIDATED -> atomic manifest/record/attempt domain commit -> PUBLISHED
-> separate final SUCCEEDED audit. STAGED refers to in-memory verified candidate bytes,
not a durable quote stage artifact or filesystem write.

Domain errors roll back record/link together but leave the original failed job.
Post-domain PUBLISHED/SUCCEEDED errors may leave content, but readers refuse it and
new writes cannot adopt it. Exact original six-phase lifecycle and original links are
required; extra scoped jobs, orphan attempts and same-source variants cannot hide in
a good subset. Publication clocks/audit metadata bind a separately reviewed recording
fingerprint, so changed clocks do not silently satisfy the original pin.

Application audit integrity is not a DB permission boundary or independently signed
root of trust against an attacker who rewrites storage and supplies new trusted pins.
No recovery/history-head, repair, force-eligible or allow-unknown bypass is introduced.

## Research-only admission and receipt replay

Native admission calls the actual pinned retained publication reader twice. Invalid,
corrupt, drifted or operational sources raise; they never turn into positive research
permission. Frozen summary retains publication/window/bundle/recording pins, policy,
row count, record clocks and explicit limitations, not a second complete 140-MB bundle.

ARCHIVED_RESEARCH_ANALYSIS can yield ACCEPTED_RESEARCH_ONLY even if all window rows
are unavailable: it permits this policy's archival analysis of the recorded snapshot,
not the existence of a usable signal or organizational authorization. The full row
statuses are in the verified publication. POINT_IN_TIME_DECISION always yields REJECTED,
even when both requested axes equal record clocks. Both axes remain required, and
naive timestamps are never assigned UTC.

Frozen receipt replay deterministically evaluates that summary only. It does not
reverify original publication content or source authenticity, consult current native
sources, authorize analysis/trading or replay strategy/risk/execution. A fabricated
internally consistent summary can reproduce offline archival acceptance. There is no
successful-summary import API in native assessment. research_analysis_authorized,
decision eligibility, availability/economic validity/coverage and replay authenticity
remain false/null.

## Independent bounds

All prior source profile limits remain unchanged.

- Complete bundle <=140000000 bytes, accommodating independently bounded inputs and
  outputs up to32MiB each under hex encoding plus bounded context/definition metadata.
- 1..16000 full inputs/outputs. Inputs <=512KiB each; outputs <=64KiB each.
- Encoded array counts/per-row/aggregate hex lengths checked before decoding.
- Nested source context <=70000 bytes (<=140000 hex characters), enforced separately.
- Native publication SQL aggregate count/byte preflight before BLOB transfer, covering
  same-publication/scope/window source rows, plus an independent per-manifest CASE guard.
- Publication request/policy each <=512 bytes; definition/contract <=32768 bytes.
- Bounded metadata inventories/LIMIT overflow and CASE-guarded audit strings/events.
- Admission frozen input and receipt independently <=32768 bytes.

JSON/hex/recomputation creates multiple copies; no streaming or peak-memory guarantee.
No unbounded export, limit inflation, automatic paging/recovery, partial or prefix success.

## Tests and verification attribution

Native tests use actual accepted disposable producer fixtures through legacy SQL,
partition Bronze, Silver, geometry Gold, persisted returns, policy windows, native bundle
assembly, publication/read/current-reader and research admission. Coverage includes
1001-row/two-partition full coverage and a real computed multi-row series; rehashed
bundle corruption/policy changes, original audit/link/contract/definition obligations,
failed review pins, extra scoped jobs, post-domain PUBLISHED/final-audit failures, actual
SQL rollback, independent SQL byte bounds, read-only/timezone and source distinctions.
These repository-native tests are supplied, NOT assistant-executed.

The pure policy suite exercises exact summary receipt replay, mandatory PIT refusal,
unknown identity/time/coverage limits, unsupported claims, source/policy shape, bounds
and the explicit offline declaration-versus-attestation distinction. Assistant pure/
isolated execution, if performed, is reported separately in the delivery response;
SQL/source adapters are not native E2E. Syntax/archive checks are not Ruff/mypy/full QA.
No independent Windows/uv-selected interpreter, repository/Git/commit/push or current
worktree-clean claim is made.

## Apply absent additions only

This ZIP contains only new implementation/tests/docs. Stop/compare if any destination
already exists. No accepted dependency, QA repair, pyproject/lock change, runtime log,
scripts/qa, PowerShell runner, per-payload SHA256 manifest or standalone verifier is
included/replaced. Preserve logs/live_status.json. Closed QA through a55f491 stays closed.

New-work repository verification:

    uv run python -c "import sys; print(sys.executable); print(sys.version)"
    uv run pytest tests/data_platform/test_legacy_window_admission.py -q
    uv run pytest tests/data_platform/test_legacy_window_publication_native.py -q
    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Check untracked additions for whitespace too. Package QA is not platform acceptance
or release of production/data/trading/authority holds.
