# Audited persisted retained market-regime Silver

## Accepted baseline, access and additive delivery

User confirmed regime Bronze QA passed and supplied 1d528db with matching reported
HEAD/origin feat/medallion-feature-store pointers. That baseline is QA CLOSED. Historical
"not run" delivery attribution does not reopen it. No independent Git/worktree/Windows
inspection, repository write, commit or push is claimed.

Access was rechecked; no repository/filesystem/execution connector was returned. Project
Sources are retrieval, not executable checkout access. A targeted retry recovered actual
current regime codec/Bronze/tests including accepted QA formatting changes. Current spot
Silver pattern, AuditLedger and DatasetContract interfaces were also inspected. Accepted
dependencies are imported unchanged, not reconstructed as replacement payloads.

Copy absent additions only; STOP and compare if a destination already exists:
- src/nse_quant/data_platform/legacy_market_regime_silver_store.py
- tests/data_platform/test_legacy_market_regime_silver.py
- docs/LEGACY_MARKET_REGIME_SILVER.md

No accepted dependency replacements, scripts/qa, PowerShell runner, per-payload manifest
or standalone ZIP verifier are included. Do not modify logs/live_status.json, infer a
real-data release or cut over consumers. This is implementation of persisted source-linked
regime Silver, not another reporting/archive wrapper.

## New contract and actual native source integration

Recording: legacy-market-regime-silver-recording@1.
Command: normalize.legacy_market_regimes@1.
Dataset: silver.legacy_market_regime_observations / 1 / APPEND_REVISIONS.
Projection: accepted legacy-market-regime-observation@1, unchanged.
Source: actual accepted legacy-market-regime-bronze-recording@1 reader, unchanged.

Complete original serialized snapshot bytes are retained in canonical context as
snapshot_hex, together with all reviewed source pins including its separate Bronze
recording fingerprint. Every source ordinal has one persisted full projection and one
materialized scalar row. No source rows/nullable fields/labels/JSON/source links are omitted.

observe_market_regime_bronze calls actual public pinned native readers before/after actual
read_recording_bytes retrieval, verifies the observed Bronze recording fingerprint,
rebuilds complete snapshot/projection context, and requires exact full projected bytes.
Persistence repeats this complete observation and requires the reviewed context hash.
Operational/corrupt upstream errors propagate under audited failed jobs, not fabricated
successful source DTOs or substituted business observations.

## All seven fields, exact text and NULL semantics

The fixed reviewed source schema is symbol, ts, trend_regime, volatility_regime, iv_regime,
regime and features. SQL generation enumerates only these accepted names/types; it is not
a caller-extensible generic normalizer.

Symbol and stored ts remain required VARCHAR/TIMESTAMPTZ. Four regime labels remain
nullable VARCHAR without enum conversion, trimming, canonical-identity interpretation or
native policy authority. Features materializes as nullable VARCHAR holding EXACT STORED
JSON TEXT, not a JSON column that parses/normalizes it. Duplicate nested keys, unknown
fields, whitespace, strings and legacy default=str output remain exact. Outer context JSON
is separately strict/canonical. Embedded eligible/authorized/available flags are never trusted.

SQL NULL, JSON text null and JSON text {} remain distinct. Source replacement history is
not recovered. Equivalent timezone spellings can replace the same stored key in the actual
legacy writer; storing normalized instants does not restore previous labels/feature blobs.
No source availability/economic truth is inferred from timestamps or legacy as-of reads.

Every materialized field is recomputed from the complete retained snapshot/projection on
read. Scalar drift rejects even when record bytes/hash remain unchanged. Exact feature
text is compared, not semantic JSON equality. Empty/unknown/whitespace labels retain the
accepted codec's flags rather than being repaired or relabeled as native regimes.

Classification stays RETAINED_LEGACY_REGIME_OUTPUT_NOT_RECOMPUTED. features_interpreted,
native_regime_recomputed and policy_authorized remain false. Canonical identity/original
availability/economic-validity instants remain null; publication/decision eligibility
remain false. No regime-policy execution, Gold feature recomputation or strategy gate is run.

## APIs and synthetic workflow

Import nse_quant.data_platform.legacy_market_regime_silver_store.

1. Construct RegimeBronzePins(source_label, snapshot_id, capture_event_id,
   envelope_hash, recording_fingerprint) from actual reviewed native Bronze evidence.
2. Open native Bronze read-only. Silver production does not open/probe current legacy SQL.
3. Explicitly call initialize_market_regime_silver(empty_file_backed_target) on a separate
   dedicated target. Existing/foreign/partial stores refuse; there is no implicit repair or
   adoption. The current catalog must itself be file-backed, not memory with a file attached.
4. Call observe_market_regime_bronze(bronze, pins=pins), review its complete context hash,
   then persist_market_regime_silver(bronze, target, pins=pins,
   expected_context_sha256=..., actor_id=..., code_revision=...).
5. Retain/review returned revision_id and recording_fingerprint SEPARATELY. Additional
   receipt fields: row_count, job_id, decision_eligibility_asserted=false.
6. Close writer owners BEFORE read-only reopen. Use read_market_regime_silver(
   readonly_silver, revision_id=..., expected_recording_fingerprint=...) for retained replay.
7. To add current native upstream equality, use revalidate_market_regime_silver(
   readonly_bronze, readonly_silver, revision_id=..., expected_recording_fingerprint=...).

Caller owns all connections, supplies no outer transaction and serializes writers. No
multi-writer coordination is asserted. Actual silver.duckdb catalog/silver schema collision
is preserved and tested, not renamed. Mutations/assertions fully quote actual
catalog.schema.table. Same-file cursor aliases reject without closing parent handles.
Code revision is a supplied full 40-character declaration; no full hash is invented from
supplied short hashes or independently authenticated Git/interpreter/issuer roots.

## Scope, atomic persistence and original obligations

First-write scope = profile + source label + snapshot ID + capture-event ID. Envelope/
recording pins, context review hash, actor/code labels and clocks are excluded. Changing
excluded fields cannot heal the same failed source-observation scope. A genuinely new
snapshot is a new revision scope, not recovery of the old failure. Label renaming is not
proof of an authenticated namespace or repaired history.

Prior scoped jobs/sets/attempt links block repeats; orphan observations for the capture
event also block adoption after sets/jobs/links are removed. No recovery, repair, retry-
adoption or orphan healing API exists. Original Bronze obligations are independently
enforced by its actual native reader. Partial initialization is not silently adopted.

Native AuditLedger job precedes actual source observation. Full context/set, every full
projection, all seven scalar indices and attempt link commit atomically in ONE domain
transaction. Failure on the second observation INSERT rolls back partial domain writes;
FAILED audit remains an original blocker. Final audit SUCCEEDED is separate from domain
commit. Its failure leaves committed rows unreadable and non-adoptable.

## Retained replay, native upstream and current legacy SQL are distinct

read_market_regime_silver requires read-only dedicated storage and exact reviewed revision/
recording pins. It validates supported definitions/contract, complete snapshot context,
full projection bytes, all scalar indices, exact source ordinal coverage/links, revision
identity, original attempt link, single scoped job and exact original
PLANNED/RUNNING/SUCCEEDED history. Missing/extra/reordered/altered/orphan rows reject.

A separate recording fingerprint binds selected context/set/observation metadata, all
scalar indices, source/context hashes, original jobs/events/links and clocks. Aware clocks
normalize with astimezone(UTC), never replace(tzinfo=UTC). Registration clocks are not
independent time truth. Retained hash/replay proves content, not authenticity of declared
Bronze pins or recovered provider bytes. Retained Silver never probes Bronze or legacy SQL
and can replay when Bronze is missing or its audit has changed.

revalidate_market_regime_silver separately requires TWO actual repeated pinned native Bronze
observations equal to frozen full context, bracketed by pinned Silver reads. Corrupt/changed
original Bronze audit fails that check even when retained Silver replays. It does not assert
current legacy SQL equality; accepted Bronze's revalidate_market_regime_source remains a
separate check. Tests mutate current legacy SQL and show native Bronze/Silver can still
match while the separate source check fails.

Sequential resource observations are NOT atomic cross-database snapshots or source-file
byte authentication. Definitions bind supported codec/source definitions and DatasetContract,
not authenticated source/interpreter/build roots, whole-repo hashes, environment recovery
or silent reinterpretation of changed definitions. No strategy/policy/risk/execution stages
were run or replayed by these APIs.

## Independent bounds and transfer ordering

Accepted regime limits are unchanged: 1..1000 complete rows; each of six text/JSON cells
<=65536 UTF-8 bytes; snapshot <=1048576 bytes; projection <=524288 bytes each and
<=4194304 aggregate. Complete hex-snapshot wrapper <=2200000 bytes. Hex length <=2097152
characters is checked BEFORE decode, followed by strict reconstruction rejecting casing/
whitespace aliases, extra fields or source label/pin mismatch.

New independent materialized scalar aggregate <=1048576 bytes. The encoded snapshot
already includes all scalar strings, so this does not inflate source limits. In one read
transaction SQL preflights count, aggregate/max record bytes, aggregate scalar bytes and
EVERY individual cell overflow BEFORE observation transfer. Independent CASE guards remain
on every materialized text, full record and source/record ID. Oversized corruption in a
formerly NULL field rejects rather than being hidden as NULL by a CASE expression.

A separate adversarial test keeps each scalar cell within its limit but exceeds aggregate
scalar bytes while full record bytes remain unchanged. Independent definition/contract/
context SQL guards and bounded catalog inventories remain. Metadata inherits <=32768
serialized bytes per independently row-bounded query. Resource overflow rejects the whole
recording, never a good subset. Bounds do not guarantee SQL scan cost, allocator/process
memory, hostile-file safety or external concurrency isolation.

## Tests and honest verification attribution

Delivered repository tests import actual DuckDBStore.write_market_regime, accepted native
Bronze producer/readers, AuditLedger/BronzeEventStore and new Silver implementation. The
positive fixture uses the actual writer to prove offset-equivalent replacement, retains
opaque duplicate-key JSON through actual SQL, then native Bronze and persisted Silver,
writer closure and read-only readers. SQL NULL/JSON null/{}, unknown labels and every
materialized scalar are reconciled without policy/eligibility interpretation.

Coverage includes mutation of EACH of seven scalars; original bytes/ordinal/coverage/context/
record/aggregate/nullable-mask faults; failed-review pin changes; source/native/retained
check separation; missing/changed Bronze; partial SQL rollback; final-audit failure;
contracts/definitions/duplicate jobs/orphans; aliases/init; hex predecode guards; scalar
aggregate preflight; and a complete actual-native synthetic maximum-label persistence test
with SHORT ID and full 65536-byte payload. Drift injection follows a real observation and
is a negative boundary, not authentic concurrent-source evidence.

Assistant-executed for this addition, isolated Python 3.12.8 / DuckDB 1.2.2:
- New implementation/test syntax compiled; addition line lengths/trailing whitespace checked.
- 22 actual SQL/materializer probes passed: full roundtrip/revalidation with NULL/JSON
  distinctions, mutation of ALL seven fields, record bytes/missing rows/clocks/orphan link,
  oversized context/record/nullable scalar, independent scalar aggregate overflow,
  failed-review non-healing, partial second-INSERT rollback, missing final audit/duplicate
  scoped job rejection, and maximum label/JSON roundtrips. Native Bronze/audit/contract
  boundaries were substituted; codec/helpers manually transcribed. These are NOT actual
  accepted-dependency native integration, actual legacy writer execution or native E2E/QA.
- ZIP exact three-member set, uniqueness, CRC, nonempty bytes and payload equality checked.

NOT run: Windows/uv interpreter check; actual repository focused/data-platform/full pytest;
actual accepted-dependency native producer/reader integration; Ruff; mypy; git diff --check;
Git untracked whitespace checks. These are NEW-package verification gaps, not pending
1d528db baseline QA. Acceptance uses uv and configured tests/lint/types plus tracked and
untracked whitespace checks. No substituted dependencies or verification wrappers are delivered.

## Remaining operational holds

This is retained regime Silver, not native regime/policy recomputation, eligible publication/
admission, authenticated governance/identity/availability, complete strategy/portfolio inputs,
native strategy/risk/execution completion, operational recovery, real-data release or cutover.
Other legacy families require their own actual schema/writer/clock contracts. Legacy loop,
accepted solvers and research-only quote/geometry/window admission contracts are unchanged.
