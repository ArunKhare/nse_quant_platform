# Audited retained feature-snapshot Bronze preservation

## Accepted baseline and bounded scope

User-confirmed QA/test CLOSED: 05423bb at reported HEAD feat/medallion-feature-store.
Reported origin remains 4986747; no push, independent Git inspection or current-worktree
claim is made. The preceding daily-RV and underlying-IV packages remain accepted.
Historical delivery-time "not run" wording does not reopen their QA.

This additive package implements a separate feature_snapshots migration contract,
read-only whole-table capture, actual native Bronze/AuditLedger production, original
recording verification, and exact source-linked IN-MEMORY projections. It is not
persisted Silver, Gold, publication/admission, recovery, strategy replay or cutover.

Access was rechecked: no repository/filesystem/execution connector was returned.
Project Sources are retrieval, not an executable checkout. Retrieval initially returned
older related daily-RV material; targeted retries recovered the actual feature schema,
MarketFeatures model, FeatureStore writer/reader and current underlying-IV Silver store.
This limitation was not treated as absence/staleness of the other requested files.
No accepted implementation is reconstructed or replaced by this package.

Copy absent additions only. STOP and compare if any destination exists. Archive contains:
- src/nse_quant/data_platform/legacy_feature_snapshots.py
- src/nse_quant/data_platform/legacy_feature_snapshot_bronze.py
- tests/data_platform/test_legacy_feature_snapshot_bronze.py
- docs/LEGACY_FEATURE_SNAPSHOT_BRONZE.md

Do not change logs/live_status.json, recreate scripts/qa, replace accepted dependencies,
add a QA runner, infer real-data release, or relabel the legacy loop as native completion.

## Actual inspected source and retained semantics

persistence/duckdb_store.py defines 22 ordered columns and a feature_id primary key:
feature_id VARCHAR; ts TIMESTAMPTZ; run_id VARCHAR; underlying VARCHAR; expiry DATE;
spot, atm_iv, iv_rank, iv_percentile, realized_vol, iv_rv_spread, pcr DOUBLE;
total_call_oi and total_put_oi BIGINT; max_pain and liquidity_score DOUBLE; regime VARCHAR;
short_momentum, straddle_price, expected_move_pct and expected_move_points DOUBLE;
diagnostics JSON. Other than the primary key, fields are nullable in retained SQL.

features/feature_store.py FeatureStore.save generates feature_id from
underlying:expiry:ts.isoformat(), then INSERT OR REPLACE writes all 22 columns.
run_id is not part of that stored key: a new run can overwrite the same key.
Diagnostics use json.dumps(default=str), and the legacy reader later parses diagnostics,
casts spot/counts, and constructs MarketFeatures. This migration does not invoke that
reader: its casts/defaults/enum construction would not preserve every retained state.

Feature IDs are opaque retained keys, NOT canonical native identity. UTC normalization
of stored ts must NOT rewrite a key that contains an original textual offset. Different
stored IDs remain different even when their stored instant matches. No recovered source
attestation or underlying/expiry/key consistency is inferred from the string format.
Overwritten revisions and their original clocks/diagnostics cannot be recovered.

All finite SQL DOUBLE values retain exact canonical binary64 hex, including signed zero.
BIGINTs retain exact signed decimal strings. NULL remains NULL, never zero or an empty
JSON object. Stored ts normalizes using astimezone(UTC), never replace(tzinfo=UTC); missing
ts remains missing and naive encoded instants reject. Expiry remains a stored DATE label,
not inferred settlement/calendar/economic-validity evidence.

Diagnostics remain EXACT STORED JSON TEXT, including whitespace, duplicate nested keys,
unknown fields, null spelling and strings produced by legacy default=str. Capture casts
the actual JSON cell to VARCHAR without parsing, rewriting, sanitizing or trusting it.
An embedded eligible/availability flag cannot grant any platform authority. Pure codecs
preserve this opaque text; they do not independently attest DuckDB JSON syntax/provider
origins. Outer artifact JSON is separately strict/canonical and rejects duplicate or
unknown structural fields. These are distinct JSON contracts.

Projection classification is RETAINED_LEGACY_FEATURES_NOT_RECOMPUTED. All analytics are
retained legacy values, not native recalculations or proven operand lineage. Negative
spread/momentum values are not globally mislabeled as invalid business observations.
Missing/whitespace identity/run/regime/time labels receive structural flags, not repairs.
There is no good-subset filtering or source-availability inference from diagnostics.

## Contracts, native integration and first-write scope

Snapshot: legacy-feature-snapshot@1.
Projection: legacy-feature-observation@1.
Bronze recording: legacy-feature-snapshot-bronze-recording@1.
Command: migrate.legacy_feature_snapshots@1.
Source: legacy_feature_table_snapshot; origin_kind=legacy_snapshot.

The new modules directly reuse the inspected accepted daily-RV strict JSON/hash/pin and
catalog/clock/path/metadata helpers. This is explicit low-level reuse, not a monkeypatch
of a family-specific reader. Actual native BronzeEvent, BronzeEventStore.append_batch and
AuditLedger plan/execution interfaces are used. Accepted dependencies are not payloads.

capture_feature_snapshots(readonly_source, source_label=...) reads the complete exact
ordered-schema BASE TABLE in a transaction. It rejects views/extra/changed columns and
types. The source must be read-only with caller-owned connection and no outer transaction.
Actual key presence/uniqueness and every cell are checked; source SQL constraint DDL is
not independently authenticated by the artifact.

preserve_feature_snapshots(readonly_source, initialized_bronze, source_label=...,
expected_snapshot_id=..., imported_at=..., actor_id=..., code_revision=...)
requires separate resources and a file-backed current target catalog. Initialize a NEW
dedicated Bronze target explicitly through actual AuditLedger.initialize and
BronzeEventStore.initialize. The producer never initializes/adopts/repairs a target.
Two actual full captures must agree with the reviewed snapshot pin.

Before native append, the producer replays the complete snapshot AND derives the full
bounded projections. Thus a snapshot that fits the evidence-byte bound but overflows a
projection bound fails under the original audit job BEFORE any native data is appended.
It cannot produce a successful receipt that the supported public projection reader cannot
consume. Escaping/resource failures reject the whole attempt, not individual observations.

Actual native append_batch retains one complete snapshot event plus the full artifact.
Import time is a supplied import receipt observation, not original provider receipt or
independent availability. exchange_ts is not fabricated from the stored feature timestamp.

First-write scope = profile + source label. Snapshot/recording/runtime pins, actor/revision
labels and clock observations are excluded. Prior scoped jobs, variants, batches or a
reviewed artifact block reuse/adoption. Changing excluded fields cannot heal a failed
scope. A new label is a new declared scope, not proof of source authenticity or recovery.
Caller serializes writes; no external multi-writer coordination is promised.

The return receipt contains source_label, snapshot_id, capture_event_id, envelope_hash,
recording_fingerprint, row_count, job_id and false decision_eligibility_asserted.
A supplied full 40-character code_revision remains a declaration, not Git attestation.

## Native original recording and current source checks

read_recording_bytes(bronze, source_label=..., snapshot_id=..., capture_event_id=...,
envelope_hash=...) reconstructs original payload/envelope and verifies stored event AND
envelope IDs, single variant, complete artifact, native batch fingerprint/counts/sequence,
single original scoped job and exact PLANNED/RUNNING/SUCCEEDED history. It is an explicit
lower-level verifier for full bytes/fingerprint, not a replacement for public read-only
and separately reviewed recording-pin requirements.

read_feature_snapshot_bronze(readonly_bronze, source_label=..., snapshot_id=...,
capture_event_id=..., envelope_hash=..., expected_recording_fingerprint=...)
checks the separate original recording fingerprint and returns one full source-linked
projection per source ordinal. Full byte/scalar projection replay is deterministic.
Recording metadata binds selected original clocks, links and hashes, not an authenticated
provider/source/interpreter/issuer/build root. No whole-repository hash scan is performed.

Source ordinals are deterministic canonical encoded-key order. Projections retain every
stored field plus source snapshot/capture-event/envelope IDs. diagnostics_interpreted and
native_features_recomputed remain false; original availability/economic-validity/identity
remain null; publication and decision eligibility remain false.

revalidate_feature_snapshot_source(readonly_legacy, readonly_bronze, **public_reader_pins)
compares two actual current full SQL captures with the original snapshot pin, bracketed
by pinned native reads. This is separate from retained replay and is not an atomic
cross-resource snapshot or source-file-byte authentication. Retained native replay can
succeed when current legacy SQL differs or is unavailable. No strategy/portfolio/risk/
execution, full-loop or positive-admission replay is asserted.

Native append/domain commit and final audit SUCCEEDED are separate. A native insert
failure rolls back event/artifact/batch writes while retaining the failed job. Missing
final SUCCEEDED after domain commit blocks original reading and repeat attempts. Original
orphan data cannot be adopted after deleting its audit. No recovery API is included.

Owners close before read-only reopen. Same-live-file aliases use distinct cursor handles,
reject without closing parent handles, and are not renamed to hide collisions. All new
mutations and test assertions quote actual catalog.schema.table names.

## Independent resource bounds

This new feature-family contract does not change any accepted family limit:
- 1..1000 complete rows; count preflight plus max+1 transfer guard.
- Each retained text/JSON cell <=65536 UTF-8 bytes.
- Aggregate transferred retained text <=1048576 bytes; all nullable columns are counted
  independently using COALESCE, never allowing NULL to hide other column bytes.
- Full canonical snapshot <=1048576 bytes, independently of raw text preflight.
- Each projection <=524288 bytes; aggregate projected records <=4194304 bytes.
  Five variable-width text/JSON fields make this a separate reviewed record shape;
  canonical escaping can still overflow and reject. No limit inflation of prior codecs.
- Envelope transfer <=8192 bytes; native bounded metadata <=32768 serialized bytes
  per query; exact small independent variant/job/history/batch/artifact row limits.

SQL preflights all text before transfer and applies independent CASE guards to cells,
payload/artifact and metadata. Decoder bounds raw artifact bytes before JSON parsing.
Primitive float/int/date/time text has independent spelling/length/type checks.
These are content/transfer bounds, not guarantees of SQL scan cost, allocator/process
memory or safety of hostile on-disk files. No paging, truncated export or partial success.

## Tests and verification attribution

Delivered tests import actual repository FeatureStore, MarketFeatures, AuditLedger,
BronzeEventStore and new implementation. Positive fixture writes with actual legacy
FeatureStore.save, deliberately overwrites a stored key from a second run, then uses
actual native capture/producer/readers. Full fixture data and assertions remain intact.
Large text parameters use explicit SHORT IDs and never clear PYTEST_CURRENT_TEST.

Coverage includes offset-bearing opaque IDs vs stored UTC instants; all retained fields;
NULL/zero/bigint boundaries; exact diagnostics including unknown/duplicate nested keys;
false authorization flags; nullable clocks; nonfinite/schema/view/key/count rejection;
original event/envelope/payload/artifact/audit/clock tampering; failed-pin non-healing;
SQL rollback and final-audit failure; aliases; orphans; canonical outer JSON; output bound
failure before append; and second actual SQL capture followed by injected drift.
The drift injection is a negative-boundary test, not authentic changed-source evidence.

Assistant execution for THIS package, isolated Python 3.12.8 / DuckDB 1.2.2:
- New implementation/tests compile; line-length/trailing-whitespace checks pass.
- 28 cases pass using the new implementation/tests and real DuckDB SQL/filesystem
  operations, BUT substituted native Bronze/Audit classes and domain model, plus
  transcribed shared helpers and inspected legacy save behavior. This is not actual
  accepted-dependency native integration, actual FeatureStore/model execution,
  repository QA or native E2E. No substitute classes are delivered.
- ZIP exact four-member set, unique names, nonempty payloads, CRC and byte equality verified.

NOT run: Windows/uv interpreter verification, actual accepted-dependency native chain,
repository focused/data-platform/full pytest, Ruff, mypy, git diff --check or Git untracked
whitespace checks. New-package repository QA is separate from CLOSED 05423bb baseline.
Use uv and configured focused/full tests, Ruff, mypy and whitespace checks for tracked
and untracked additions for acceptance. Do not recreate scripts/qa.

## Remaining boundary and operational holds

Persisted source-linked feature Silver remains a subsequent chunk; these projections are
not a fake DatasetContract or persisted Silver claim. Native feature recomputation requires
its own sufficient source/definition/domain contract, not relabeling retained values.
No original overwritten history, authenticated governance/identity/availability, PIT
admission, native strategy/risk/execution completion, real-data migration release, consumer
cutover or full-platform completion is claimed. Legacy loop and native solvers are unchanged.
