# Native persisted legacy-market Silver @1

## Baseline and scope

User reports HEAD/origin feat/medallion-feature-store at 5376f60:
feat(data-platform): add audited native preservation of legacy market snapshots.
User confirms repository QA/tests passed. 75a5d71 is the supplied documentation
commit. Only short hashes were supplied; no full hash or independent Git inspection
is claimed. Current Sources legacy_market_snapshot.py and its tests were inspected,
including the committed codec's tuple-destructuring change. They are NOT replaced.

This package adds persisted Silver legacy observations from the actual verified
native Bronze snapshot reader. It is not another exporter/inspection wrapper or
legacy-workspace adapter. It does not reconstruct accepted native-input/risk work.
No scripts/qa, checksum manifest or standalone verifier is added.

Pipeline implemented:

    synthetic legacy SQL -> accepted native Bronze preservation
      -> actual verified native Bronze reader
      -> exact legacy Silver projection
      -> audited dedicated persisted set + every source ordinal
      -> read-only recording verification / separate current Bronze revalidation

Existing whole-table limits remain 1..1000 selected legacy rows, not production
partitioning. No paging, latest-good selection, row omission or partial promotion.
Real-data migration/loading/backfill remains HELD. Only disposable synthetic QA
was executed. No acquisition, registrations, Gold publication, strategy cutover
or trading occurs. No positive decision-admission lane is added.

## Files and public interfaces

legacy_market_silver.py: pure LegacyBronzePins, derive_records, record_values and
versioned bounds/definition. Pure constructors accept untrusted observations;
content validity does NOT attest that they were read from a native source.

legacy_market_silver_store.py:

    initialize_legacy_silver(empty_target)
    observe_legacy_bronze(bronze, pins=...) -> exact_context_bytes
    persist_legacy_silver(bronze, target, pins=...,
        expected_source_context_sha256=..., actor_id=..., code_revision=...)
    read_legacy_silver(source, revision_id=..., expected_recording_fingerprint=...)
    revalidate_legacy_silver(bronze, silver, revision_id=...,
        expected_recording_fingerprint=...)

Review the exact bytes from observe_legacy_bronze before supplying their SHA-256.
A fingerprint produced by a caller is not independent authority or issuer approval.
Code revision must be an explicit reviewed lower-hex 40-character revision; the
supplied short baseline is NOT silently padded or used as a full reviewed revision.

There is no prebuilt-successful-result import API in the persistence service.
It calls the actual read_preserved_legacy_snapshot and recomputes records itself.
Caller owns dedicated file-backed connections, no enclosing transactions or
concurrent writers. Source readers require actual read-only connections. Source
and target files/attached aliases must not overlap. No automatic DB opening or CLI.
Initialization requires empty target. Audit creation, Silver schema creation and
contract registration are separate; interrupted initialization is not adopted.

## Silver contract and reconciliation

The existing DatasetContract API registers silver.legacy_observations with
APPEND_REVISIONS, revision/ordinal identity and required source-observation/recording
metadata. Each source ordinal has exactly one record. Complete source-table field
membership, exact scalar encodings and original derived-field projection must match.
Duplicate or unknown legacy keys refuse the WHOLE set. Ordinals are the canonical
Bronze snapshot ordinals, not an invented original event ordering.

Materialized SQL columns include provider token, stored timestamp, volume and OI,
plus record identity and full exact bytes. Every index/scalar is rederived and
compared with the complete stored bytes. Token is a provider identifier only.
DOUBLE prices and stored analytics remain exact finite binary64 HEX, not a guessed
original decimal/integer-provider-price representation. Signed zero stays distinct.
NULL and observed zero stay distinct. JSON text is retained, not parsed/reformatted.
The original source field dictionary, including iv/delta/gamma/vega/theta, remains
available; those analytics are explicitly legacy-derived, not native recalculation.

Classification is RETAINED_LEGACY_OBSERVATION_NOT_MARKET_VALIDATED. Preserved finite
negative/inconsistent market values are not approved for financial consumption.
canonical_contract_id remains null. Availability, economic-validity, publication
and decision-eligibility flags remain false. Stored market ts is not independent
availability evidence. SQL TIMESTAMPTZ compares instants, normalizing to UTC for
canonical metadata; no replace(tzinfo=UTC) conversion is used.

## Full reviewed source context

The actual native reader brackets bounded metadata capture and the producer
repeats the complete source observation. Retained context includes every returned
legacy observation, exact pins, complete selected event-envelope metadata, ingest
ordinal/clocks, original job/audit history, original batch metadata and artifact
recording metadata. It includes observed Python/DuckDB versions. Review pin and
complete canonical bytes must agree across passes: equal policy status or equal
prices alone cannot hide metadata drift.

The context retains full projected source DTOs and recording metadata, NOT the
full original Bronze artifact payload bytes. Those remain in Bronze and are
reverified by the actual existing reader. Do not claim complete retained-original
Bronze lifecycle replay from this Silver context. The source reader's existing
verification scope/limitations are inherited, not silently upgraded. No source-code
build attestation or independently authenticated provider/identity/time claim.

Sequential checks are not atomic cross-database snapshots. Sources may change
after the final observation. Bounded lazy result scans and per-field metadata
validation do not establish total SQL scan-cost/runtime/process-memory ceilings.

## First-write and audit semantics

Scope binds Silver version and exact Bronze event/envelope/snapshot pins.
Existing scope set/job/attempt refuses before any native source observation.
Existing rows for the same source event also block, including orphan rows.
Original failed, running, planned, cancelled or unlinked obligations cannot be
filtered out or healed by a later successful request. No retry/adoption,
supersession, cleanup, rollback-repair or original-obligation replacement API.

Set + every observation + attempt link commit in one domain transaction.
Final audit success is separate. A final-audit failure can leave complete domain
records with RUNNING audit; readers refuse them, and a later call cannot adopt them.
A failure during row write preparation rolls back set/rows/attempt but retains the
failed original audit. A new reviewed source scope is not repair of an old one.

A Silver revision binds definition, exact source context and all record hashes.
Recording readers also require a separately reviewed full recording fingerprint,
which binds recording clocks, jobs, links and audit history. Complete ordinal/row
coverage, exact stored indices and recomputation equality are mandatory. Original
metadata changes are not accepted by refreshing a reviewed fingerprint automatically.
Privileged SQL mutation, deletion or whole-file rollback is not prevented.

## Recording verification versus current revalidation

read_legacy_silver verifies the retained Silver recording and rederives all records
from its retained projection. It does not read current Bronze or the old database.
This can remain valid after current source evidence is invalidated: that is an
original-recording claim, NOT current-source eligibility.

revalidate_legacy_silver verifies the recording, performs repeated actual Bronze
checks requiring complete equality with the original reviewed source context, then
rechecks the Silver recording. It never refreshes context or selects later-good
sources. Operational SQL/IO failures propagate rather than becoming policy success.
Neither method proves issuer authority, canonical identity, complete market history,
source-file original bytes, strategy/risk approval or complete platform replay.

## Resource bounds

- 1..1000 source observations, unchanged from the accepted Bronze snapshot profile.
- <=64 KiB text cell, <=512 KiB encoded Silver record.
- <=4 MiB projected source observations; <=8 MiB complete source context.
- <=8 MiB aggregate Silver record bytes; aggregate SQL preflight before row transfer.
- Dedicated inventory is eight known base tables; bounded limit+1 discovery.
- Exactly one scoped original Silver job/link and three successful lifecycle events.
- Metadata result fetches use limit+1 and per-field checks; not global memory limits.

Large real datasets still require an explicit partition/coverage contract. Do not
raise limits or label a partial table as complete to make real migration succeed.

## Verification ledger

Assistant executed 27 projection/actual disposable SQL-materialization tests:
PASSED under Python 3.12.8 and DuckDB 1.2.2. Includes both table
profiles, full ordinal coverage at 1000 rows, signed zero, null/zero, legacy-derived
analytics, timezone instant equality, duplicate/unknown keys, malformed stored
cells, promoted source flags, source-pin changes and real aggregate byte bounds.
These tests are NOT execution of native Bronze-to-Silver persistence.

23 native pipeline/failure cases are supplied for repository QA, NOT executed
by assistant here. They seed actual accepted legacy -> Bronze producers and use
actual Bronze readers, Silver schema/contract/audit, persistence and revalidation.
No successful reader or native computation result is substituted. Fault injections
only raise failures at actual final audit or row-write preparation boundaries.
Tests cover both tables, retained/current separation, same-price metadata drift,
scalar/bytes/count/link corruption, missing terminal audit, contract drift, scoped
PLANNED/RUNNING/FAILED/CANCELLED unlinked obligations, first-write ordering,
rollback/final-audit failures, orphan blocking, timezone/fingerprint checks,
same-live-file cursor alias refusal/parent usability and source SQL failure.

Current connector discovery exposed no repository/filesystem/terminal connector.
No local Windows CPython 3.14.2 execution or repository Git inspection. Full pytest,
Ruff, mypy and git diff --check NOT RUN. Actual syntax/line-length/whitespace and
ZIP CRC/exact members/payload equality checks performed. No accepted production
source was reconstructed into the delivery, overwritten or modified.

Review ABSENT additions only; stop/compare if a target already exists. Then:

    uv run pytest tests/data_platform/test_legacy_market_silver.py tests/data_platform/test_legacy_market_silver_native.py -q
    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Also check untracked whitespace; git diff --check does not cover untracked files.
Preserve logs/live_status.json. No automatic staging, cleanup, commits or pushes.
Package QA does not release the real-data migration hold or establish platform acceptance.
