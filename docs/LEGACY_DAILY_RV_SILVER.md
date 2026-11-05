# Persisted retained daily-RV Silver

## Accepted baseline and additive scope

User confirmed QA/tests passed at 4c94547, with matching reported HEAD/origin pointers
on feat/medallion-feature-store; ecadafd is the accepted daily-RV codec predecessor.
Those accepted packages remain QA CLOSED. Historical delivery-time "not run" text
in their documentation does not reopen acceptance. No independent Git or Windows
checkout inspection was available for this addition.

This package adds one native persisted Silver implementation, its actual-native
synthetic integration/adversarial test module, and this document. Accepted daily-RV
codec, Bronze adapter, AuditLedger, contracts and other dependencies are NOT payloads.
Copy absent additions only. STOP and compare if any destination exists; no overwrite,
cleanup, scripts/qa recreation or changes to logs/live_status.json are authorized.

## Contract

Recording profile: legacy-daily-rv-silver-recording@1.
Command: normalize.legacy_daily_rv_silver@1.
Dataset: silver.legacy_daily_rv_observations / 1 / APPEND_REVISIONS.
Projection codec: accepted legacy-daily-rv-silver@1.
Source: accepted legacy-daily-rv-bronze-recording@1 native original-recording reader.

The complete original serialized SQL snapshot is retained in canonical context as
snapshot_hex. The wrapper retains all reviewed Bronze pins, including the separately
reviewed original Bronze recording fingerprint. Every source ordinal gets exactly one
persisted observation. The projection codec is not replaced or weakened.

Classification stays RETAINED_LEGACY_DERIVED_RV_NOT_RECOMPUTED. Stored RV is finite
binary64 hex, including signed zero, NOT native recomputation or recovered provider
precision. Missing/invalid input is not imputed. Negative/zero RV and nonpositive counts
are retained and flagged by the accepted codec. DATE stays a stored date label; it is
never converted to a timezone or asserted to be an authoritative trading session.
Original overwritten history, availability, independent market coverage, canonical
identity, statistical-method/annualization validity and economic validity remain unknown
or false as specified by that codec. There is no publication or positive decision lane.

## API and synthetic workflow

Import nse_quant.data_platform.legacy_daily_rv_silver_store.

1. Construct DailyRVBronzePins(source_label, snapshot_id, capture_event_id,
   envelope_hash, recording_fingerprint) from the actual Bronze producer receipt and
   explicit review. All pins are exact lower-case SHA256 values except the source label.
2. Open the native Bronze database read-only. The producer never accesses legacy SQL.
3. Open a separate, empty, file-backed Silver target and explicitly call
   initialize_daily_rv_silver(target). It refuses existing tables, foreign objects,
   partial initialization and implicit adoption. Initialization failures are not repaired.
4. Call observe_daily_rv_bronze(bronze, pins=pins), review its context hash, then call
   persist_daily_rv_silver(bronze, target, pins=pins,
   expected_context_sha256=..., actor_id=..., code_revision=...). Code revision must be
   a supplied full 40-character lower-case hash; it is a declaration, not authenticated Git.
5. Retain and review the returned revision_id and recording_fingerprint separately.
   Return fields also include row_count, job_id and decision_eligibility_asserted=false.
6. Close writer owners before opening read-only readers. Call
   read_daily_rv_silver(readonly_silver, revision_id=...,
   expected_recording_fingerprint=...) for retained replay.
7. To make the additional current-native-Bronze equality check, call
   revalidate_daily_rv_silver(readonly_bronze, readonly_silver, revision_id=...,
   expected_recording_fingerprint=...).

Caller owns all connections, provides no outer transactions, and serializes writes.
These APIs are not a CLI, a multi-writer coordinator or real-data import authorization.
The actual silver.duckdb catalog/silver schema collision is preserved and tested using
fully quoted actual catalog.schema.table names. Same-file cursor aliases reject without
closing the parent. A memory current catalog cannot qualify merely by attaching a file.

## Native source integration

observe_daily_rv_bronze calls the actual public pinned read_daily_rv_bronze reader,
then the inspected original _recording API to recover the full validated snapshot,
then the public reader again. It checks the recovered recording fingerprint, rebuilds
the complete context/projection, and compares all projected bytes with both native reads.
The inspected private source API is an explicit @1 dependency, not a copied replacement.
Operational/corrupt native-source errors propagate; they do not become successful DTOs.

Persistence performs this whole observation twice around the reviewed-context check.
Audit jobs exist before source observation, so failed observations retain original
obligations. Snapshot context, set, every full observation, typed scalar indices and
attempt link commit atomically in the domain transaction. Audit SUCCEEDED occurs separately.

## Scope, immutable revisions and failure obligations

First-write scope = profile + source label + snapshot ID + capture-event ID.
It excludes envelope/recording pins, context review hash, actor/revision labels and clocks.
Changing those excluded fields cannot heal the same failed source-observation scope.
A different source snapshot is a different declared revision scope, not recovery.
Prior scoped jobs, sets and attempt links block reattempts. Existing records for the
capture event also block adoption even if sets/jobs/links have been removed.

No successful retry, repair, recovery or orphan adoption is provided. A native record
identity is not an authenticated source root. Scope and source labels are declarations;
renaming them is not proof of repaired or complete history. Original Bronze first-write
obligations are enforced independently by its actual reader.

The test fault on the second observation INSERT exercises partial domain writes and
rollback of set, observations and attempt link. The FAILED audit job remains a blocker.
A failure of final SUCCEEDED after domain commit leaves an unreadable original recording;
changing pins or invoking persistence again cannot adopt it.

## Retained replay versus current upstream

read_daily_rv_silver requires a read-only dedicated Silver database. It validates current
schema/contract definitions; reads the complete bounded context; reconstructs the accepted
snapshot and every record; verifies exact ordinal coverage, full bytes, source links and
all typed scalar indices; reconstructs revision identity; and verifies original scoped
job, exact PLANNED/RUNNING/SUCCEEDED history and attempt link.

The separately reviewed recording fingerprint binds the retained context, selected set/
observation metadata and clocks, links, original job and event history. Stored DATE scalar
indices are encoded as ISO date labels in the fingerprint, not passed to the timestamp
serializer. All clock observations must be aware and normalize using astimezone(UTC).
Schema registration timestamps are not asserted to be authenticated provenance.

Offline snapshot replay proves retained content, not the authenticity of declared Bronze
recording pins. The retained Silver reader deliberately does not probe Bronze or legacy
SQL. It can replay after Bronze is missing or its audit has changed.

revalidate_daily_rv_silver separately requires two actual repeated pinned native Bronze
observations equal to the frozen full context, bracketed by pinned Silver reads. Corrupt
or changed original Bronze audit must then fail. Sequential observations are NOT an atomic
cross-database snapshot. No current legacy SQL, original provider-byte authentication,
strategy/portfolio/execution replay or operating authorization is asserted.

Definitions bind the inspected codec/source definition and actual DatasetContract. This
profile does not promise authenticated source/interpreter/build attestation, whole-repo
hash coverage, environment recovery or silent reinterpretation of changed definitions.

## Independent bounds

All accepted codec limits remain unchanged:
- 1..1000 source rows and exactly that many persisted observations.
- Snapshot <=1048576 bytes; symbol <=65536 UTF-8 bytes.
- Each projected observation <=70000 bytes; aggregate <=4194304 bytes.
- Complete hex-encoded snapshot wrapper <=2200000 bytes.
- Hex length is checked <=2097152 characters before bytes.fromhex; strict canonical
  wrapper reconstruction rejects spaces, uppercase alternatives, extra keys and drift.
- Definition/contract SQL transfers <=32768 bytes each; source metadata bounds remain
  independently enforced by the accepted native Bronze reader.

Before observation transfer, SQL preflights count and sum(octet_length(record_bytes)).
Independent CASE guards bound context, record bytes, scalar strings and audit metadata;
metadata queries have small independent LIMITs. Non-null audit parent/reason values use
rejection sentinels, never silently converted to acceptable NULL. Row-size and aggregate
failures reject the whole recording, not business observations or a good subset.

These bounds do not guarantee SQL scan cost, allocator/process memory ceilings, hostile
on-disk file safety or concurrency isolation across independent resources.

## Tests and honest verification

The delivered test module imports actual accepted codec, Bronze/AuditLedger producer and
reader APIs. Its synthetic chain creates retained SQL, captures/preserves native Bronze,
persists native Silver, closes writers, opens read-only readers and revalidates both layers.
Other tests cover full-byte/scalar/ordinal/context/link/clock/audit tampering; changed or
missing Bronze vs retained replay; failed-scope pin changes; orphan records; aggregate and
record bounds; original job duplication; contract/definition drift; cursor aliases; partial
SQL rollback; separate final-audit failure; maximum 65536-byte symbol with a short pytest
ID; and hex predecode guards. Full payloads/assertions are preserved.

The drift test invokes the actual source observation before injecting changed returned
bytes. It is a negative-boundary test, not authentic changed-source evidence.

Assistant-executed checks for THIS package:
- Compilation of the new implementation and tests under isolated Python 3.12.8.
- Ten actual DuckDB 1.2.2 materializer probes: roundtrip/revalidation, scalar/byte/clock
  tampering, orphan link, missing row, oversized context/record, failed-review non-healing,
  and SQL domain rollback. These used substituted Bronze/audit/contract boundaries and a
  manually transcribed codec. They are NOT actual native integration or native E2E.
- The initial isolated roundtrip exposed DATE fingerprint serialization; it was fixed
  without assigning timezone semantics and all ten probes were rerun successfully.
- Addition line-length/trailing-whitespace checks and final archive exact member set,
  unique names, CRC, nonempty bytes and payload equality checks.

NOT run: actual repository native integration tests, Windows/uv interpreter verification,
focused pytest, data-platform/full suites, Ruff, mypy, or git diff --check. No repository
write/commit/push or current-worktree cleanliness claim is made. User-confirmed baseline
QA at 4c94547 remains closed; new-package QA is a separate acceptance obligation.

Repository validation should use uv and the project's configured focused/full tests,
Ruff, mypy and whitespace checks, including untracked additions. No scripts/qa is created.
Native RV Gold, publications/admission, operational recovery, real-data migration release,
consumer cutover and positive native strategy/risk/execution remain outside this package.
