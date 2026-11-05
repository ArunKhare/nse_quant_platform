# Audited persisted retained feature-snapshot Silver

## Baseline, delivery and scope

User confirmed feature Bronze QA passed and supplied de3f6d8 with matching reported
HEAD/origin on feat/medallion-feature-store. Treat that baseline as QA CLOSED. Historical
"not run" attribution in accepted delivery documents does not reopen acceptance.
No independent Git/worktree/Windows inspection, repository write, commit or push is claimed.

Access was rechecked; no repository/filesystem/execution connector was available. Project
Sources were retrieval only. Initial retrieval returned related older Silver files; a
targeted retry recovered the actual current feature codec, Bronze source and tests,
including accepted formatting/QA changes. They are reused unchanged, not reconstructed
as replacement payloads. Current AuditLedger and DatasetContract interfaces were inspected.

This package adds actual persisted feature Silver, not a summary/archive wrapper:
- src/nse_quant/data_platform/legacy_feature_snapshot_silver_store.py
- tests/data_platform/test_legacy_feature_snapshot_silver.py
- docs/LEGACY_FEATURE_SNAPSHOT_SILVER.md

Copy ABSENT additions only. If any destination exists, STOP and compare; do not overwrite.
Accepted codec/Bronze/native dependencies are not payloads. Do not modify
logs/live_status.json, recreate scripts/qa, add a QA runner/manifest/standalone ZIP verifier,
change accepted contracts, infer real-data release or cut over the legacy loop.

## New recording contract

Recording: legacy-feature-snapshot-silver-recording@1.
Command: normalize.legacy_feature_snapshots@1.
Dataset: silver.legacy_feature_observations / 1 / APPEND_REVISIONS.
Projection: accepted legacy-feature-observation@1, unchanged.
Source: actual accepted legacy-feature-snapshot-bronze-recording@1 reader.

The complete original serialized SQL snapshot is retained in canonical context as
snapshot_hex, together with all reviewed source pins including the separate Bronze
recording fingerprint. Every original source ordinal has exactly one persisted full
projection and materialized scalar row. No source rows, unavailable fields, diagnostics,
flags or lineage are silently filtered, bridged, padded or imputed.

## All 22 fields are reconciled

Silver materializes every field in the inspected fixed feature schema:
feature_id, ts, run_id, underlying, expiry, spot, atm_iv, iv_rank, iv_percentile,
realized_vol, iv_rv_spread, pcr, total_call_oi, total_put_oi, max_pain, liquidity_score,
regime, short_momentum, straddle_price, expected_move_pct, expected_move_points, diagnostics.

The layout is FIXED by that accepted schema/definition, not a caller-extensible generic
normalizer. Dynamic SQL generation only enumerates these reviewed names and types.
- DOUBLEs use nullable VARCHAR hex, not SQL DOUBLE roundtrips: signed zero and exact
  retained binary64 spelling survive. No provider-decimal/tick-precision claim.
- BIGINTs materialize as exact signed BIGINT, with full encoded strings retained in bytes.
- ts is nullable TIMESTAMPTZ; expiry is nullable DATE, with no invented defaults.
- Opaque feature_id remains required; all other source fields preserve actual NULL.
- diagnostics is nullable VARCHAR holding exact stored JSON TEXT, not a JSON column
  that normalizes/reformats it. It is never parsed for admission, identity or availability.

All materialized fields are recomputed from full retained snapshot/projection bytes on
read. SQL scalar drift is not allowed even when the stored record bytes/hash still match.
The tests independently mutate each of the 22 scalar columns to prove reconciliation.

FeatureStore source keys remain opaque. An ID can contain +05:30 while stored ts is a UTC
instant; the ID is never regenerated from normalized time. run_id is not a revision key.
Actual INSERT OR REPLACE history cannot be recovered. Duplicate/unknown nested diagnostic
keys and whitespace remain original text, not outer contract fields. Outer context JSON
is separately strict/canonical. Retained diagnostics cannot authorize anything.

Classification remains RETAINED_LEGACY_FEATURES_NOT_RECOMPUTED. Native recomputation and
diagnostics interpretation remain false. Original availability, economic validity and
canonical identity remain null. Publication/decision eligibility remain false. Nullable
clocks are observations, not unavailable data silently assigned UTC or import time.

## APIs and native source integration

Import nse_quant.data_platform.legacy_feature_snapshot_silver_store.

1. Construct FeatureBronzePins(source_label, snapshot_id, capture_event_id,
   envelope_hash, recording_fingerprint) from actual reviewed native Bronze evidence.
2. Open Bronze read-only. No legacy SQL is needed or probed by the Silver producer.
3. Explicitly initialize a separate EMPTY file-backed dedicated target with
   initialize_feature_snapshot_silver(target). Partial/foreign/existing stores refuse;
   no initialization repair/adoption is offered. The current catalog must itself be
   file-backed; attaching a file to an in-memory current catalog is insufficient.
4. Call observe_feature_snapshot_bronze(bronze, pins=pins), review the complete context
   hash, then persist_feature_snapshot_silver(bronze, target, pins=pins,
   expected_context_sha256=..., actor_id=..., code_revision=...).
5. Retain/review returned revision_id and recording_fingerprint separately. Receipt also
   includes row_count, job_id and decision_eligibility_asserted=false.
6. Close writer owners BEFORE read-only reopen. Call read_feature_snapshot_silver(
   readonly_silver, revision_id=..., expected_recording_fingerprint=...) for retained replay.
7. To add current native upstream verification, call revalidate_feature_snapshot_silver(
   readonly_bronze, readonly_silver, revision_id=..., expected_recording_fingerprint=...).

observe_feature_snapshot_bronze calls actual public pinned native readers before/after
actual read_recording_bytes retrieval. It verifies the original Bronze fingerprint,
rebuilds full context/projections, and requires exact projected bytes throughout.
Persistence repeats this complete native observation and requires the reviewed context.
Operational/corrupt upstream failures propagate under an audited failed attempt; they
are not fabricated successful source DTOs or substituted business observations.

All connections belong to the caller, with no outer transactions or shared writer owners.
Caller serializes writers. Actual silver.duckdb catalog/silver schema collision is preserved
and tested, not renamed. All new mutations/assertions use actual quoted
catalog.schema.table. Cursor aliases reject without closing parent handles.

## Atomic persistence, scope and original obligations

Scope = profile + source label + snapshot ID + capture-event ID. Envelope/recording pins,
context review hash, actor/code labels and recording clocks are excluded. Changing those
excluded fields cannot heal the same failed source-observation scope. A genuinely new
source snapshot is a new source revision, not recovery of the original obligation.

Prior scoped jobs/sets/links block reattempts; orphan observations for the capture event
also block adoption when sets/links/jobs are removed. Neither label changes nor a new
reviewed fingerprint proves authenticated roots or repaired history.

Native AuditLedger job precedes actual source observation. The complete context/set,
every full projection, all scalar indices and attempt link commit in ONE domain
transaction. Failed partial observation INSERTs roll back all domain writes while
retaining the FAILED job. Final audit SUCCEEDED remains separate from domain commit.
A final-audit failure leaves committed rows unreadable and non-adoptable. No implicit
retry, recovery, healing or orphan adoption API exists. Initialization failures likewise
require separate explicit handling; this package never adopts partial initialized stores.

## Retained replay versus current upstream

read_feature_snapshot_silver requires a read-only dedicated target and exact reviewed
revision/recording pins. It verifies current supported definitions/contract, complete
snapshot context, projection bytes, ordinal coverage, every scalar, source observation
links, revision identity, original attempt link, single scoped job and exact original
PLANNED/RUNNING/SUCCEEDED history. Missing/orphan/extra/reordered/tampered rows reject.

The separate recording fingerprint binds context hash, selected set/observation metadata,
all retained scalar indices, original jobs/events/links and recording clocks. DATE indices
serialize as date labels; nullable aware timestamp indices normalize via the accepted
clock serializer. No replace(tzinfo=UTC) or fabricated dates/instants. Schema registration
clocks are not independently authenticated provenance.

The full snapshot hash/replay proves retained content, NOT authenticity of declared source
recording pins. Offline Silver reading never probes Bronze or legacy SQL and can work
when Bronze is missing or its audit no longer validates.

revalidate_feature_snapshot_silver separately requires two actual pinned current native
Bronze observations to equal frozen full context, bracketed by pinned Silver reads.
It does not compare current legacy SQL. Accepted Bronze's separate current-legacy-SQL
revalidation remains distinct. Sequential resource observations are not an atomic
cross-database snapshot or source-file-byte authentication.

Definitions bind the supported codec/source definition and actual DatasetContract, not an
authenticated Git/interpreter/issuer root, whole-repository hash inventory, environment
recovery or silent reinterpretation of changed definitions. Code revision is supplied as
an exact full 40-character declaration; no full hash is invented from supplied short hashes.

## Independent resource/transfer bounds

Accepted feature source limits are unchanged: 1..1000 rows; text cells <=65536 UTF-8 bytes;
full canonical snapshot <=1048576 bytes; projection <=524288 bytes each and <=4194304
bytes aggregate. New full hex-snapshot context <=2200000 bytes; hex length <=2097152
characters checked BEFORE decode, then strict wrapper reconstruction rejects aliases,
whitespace, extra fields and source label/pin mismatch.

This store independently caps aggregate materialized variable-width scalar bytes at
1048576 bytes. Encoded snapshots already include those scalar strings, so this bound
adds a transfer check without expanding source limits. SQL preflights record count,
aggregate/max full-record bytes, aggregate scalar bytes and ALL per-cell overflows in
the SAME read transaction BEFORE transferring observation rows. Independent CASE guards
remain on every materialized string, record bytes and source/record IDs.

Importantly, oversized corrupt values are rejected by preflight, not converted to NULL
by a CASE expression and accidentally accepted as an original nullable cell. This is
explicitly tested for a formerly NULL run_id. Contract/definition/context/metadata have
independent SQL guards and small row limits. Catalog object-name inventories are bounded
before transfer as well. No good-subset success or unbounded exports are supported.

These are content/transfer bounds, not guarantees of database scan cost, allocator/
process memory, hostile on-disk safety or multi-writer coordination.

## Tests and honest verification attribution

Delivered repository tests import actual MarketFeatures/FeatureStore, accepted feature
Bronze producer/reader, native AuditLedger/BronzeEventStore and new Silver implementation.
The synthetic chain includes actual legacy writes/overwrite, retained nullable SQL row,
native Bronze capture/preservation, persisted Silver, owner closure and read-only readers.

Coverage includes all 22 scalar mutations; opaque offset-bearing IDs; signed zero/NULL/
BIGINT extremes; exact duplicate-key diagnostics; nullable timestamps/dates; original
scope pin changes; full bytes/coverage/context/record/aggregate/NULL-mask tampering;
current-Bronze vs retained replay separation; missing Bronze; partial second-INSERT SQL
rollback; final-audit failure; source drift injection; definitions/contracts/duplicate
jobs/orphan records; alias/initialization rules; and hex predecode limits.
The maximum-text scalar test is explicitly a projection/scalar-boundary check, NOT a
persisted maximum-text native E2E claim. Large payloads keep full assertions and SHORT IDs.
Drift injection occurs after real observation; it is not authentic changed-source evidence.

Assistant-executed independent checks for this package:
- New implementation/tests compile under isolated Python 3.12.8.
- 32 actual DuckDB 1.2.2 SQL/materializer probes passed, including mutations of ALL 22
  fields, complete roundtrip/revalidation, record bytes, missing rows, clocks, orphan link,
  oversized context/record/nullable scalar, failed-review non-healing and partial rollback.
  Bronze/audit/contract boundaries were substituted; codec/helpers manually transcribed.
  These are NOT actual accepted-dependency native integration or repository E2E/QA.
- Additional roundtrip checked the final bounded catalog-inventory guard.
- Addition line lengths/trailing whitespace, archive exact three-member set/uniqueness,
  CRC, nonempty payloads and payload-byte equality checked.

NOT run: Windows/uv interpreter check, actual native producer/reader integration,
repository focused/data-platform/full pytest suites, Ruff, mypy, git diff --check or Git
untracked whitespace checks. No substitute dependencies are delivered. Required new-package
acceptance uses uv and configured tests/lint/types/whitespace checks, including untracked
additions. No accepted de3f6d8 QA is pending or reopened.

## Operational holds

This is retained feature Silver, not Gold native recomputation, eligible publication,
authenticated governance/identity/availability, complete strategy/portfolio inputs,
native strategy/risk/execution replay, operational acceptance, real-data release or cutover.
Legacy loop and accepted numerical solvers/quote/window admission contracts stay unchanged.
