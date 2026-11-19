# Audited layout-explicit retained regime-policy Silver

## Accepted baseline, updated source and additive delivery

User confirmed 8489d2f policy Bronze QA passed and supplied matching HEAD/origin
feat/medallion-feature-store pointers. ce4bd29 is the supplied accepted regime Silver
predecessor. Both remain QA CLOSED; historical delivery-time "not run" statements do not
reopen acceptance. No full hashes, independent Git/worktree/Windows inspection, repository
write, commit or push are claimed.

Access was rechecked: no repository/filesystem/execution connector was available. Project
Sources remain retrieval only. After the user's Sources update and targeted retries, actual
current legacy_regime_policies.py, legacy_regime_policy_bronze.py and their tests were
recovered, including accepted QA formatting/fixture changes. They are imported unchanged;
previous generated payloads are not accepted-dependency replacements.

Copy absent additions only. STOP and compare if any destination exists:
- src/nse_quant/data_platform/legacy_regime_policy_silver_store.py
- tests/data_platform/test_legacy_regime_policy_silver.py
- docs/LEGACY_REGIME_POLICY_SILVER.md

No scripts/qa, PowerShell runner, per-payload manifest, standalone ZIP verifier or dependency
replacement is included. Do not modify logs/live_status.json, infer real-data release,
repair the legacy positional writer or cut over consumers.

## Contract and meaningful native integration

Recording: legacy-regime-policy-silver-recording@1.
Command: normalize.legacy_regime_policies@1.
Dataset: silver.legacy_regime_policy_observations / 1 / APPEND_REVISIONS.
Projection: accepted legacy-regime-policy-observation@1, unchanged.
Source: actual legacy-regime-policy-bronze-recording@1 original-recording reader, unchanged.

This is actual persisted source-linked Silver, not a summary/report/archive wrapper or
fake Gold contract. Full original serialized snapshot bytes are retained as canonical
snapshot_hex context alongside all reviewed pins. The snapshot itself retains exact
physical_columns, canonical columns and reviewed layout_id. Every source ordinal has one
persisted full projection, all eleven materialized source fields and source_layout_id.

observe_regime_policy_bronze calls actual public pinned native readers, actual
read_recording_bytes retrieval, verifies the observed recording fingerprint, reconstructs
full context/projections, and repeats the public read. All projected bytes must match.
Persistence repeats this complete native observation and requires the reviewed context
hash. Corrupt/operational upstream failures propagate under audited failed jobs, never
fabricated successful source DTOs or policy permission.

## Layout and scalar semantics

The eleven fixed reviewed source fields are policy_id, symbol, train_start, train_end,
test_start, test_end, allowed_regimes, regime_metrics, selection_status, risk_limits,
created_at. SQL generation enumerates only the accepted fixed schema, not caller-supplied
fields or an arbitrary codec. Policy_id is required; remaining nullable fields stay NULL.

Both accepted explicit source layouts are supported:
- risk-before-clock: risk_limits JSON before created_at TIMESTAMPTZ.
- clock-before-risk: created_at TIMESTAMPTZ before risk_limits JSON.

Silver does not guess a layout or repair/reorder source writes. PolicyBronzePins contains
layout_id; actual source reader verifies it. Full frozen context reconciles it with the
snapshot's physical schema and every projection. Every materialized source_layout_id is
compared with the recomputed observation. Changing only the materialized layout, reviewed
layout pin or frozen physical_columns rejects. Source identity includes complete artifact
bytes, so equal named values under different physical layouts are not one recording.

The inspected legacy positional-writer mismatch remains unchanged. The matching appended
layout fixture uses actual RegimePolicy and DuckDBStore.save_regime_policy; the fresh-layout
positive fixture uses NAMED synthetic SQL, explicitly not a repaired positional writer.
No new source-writer method, historical value swap, permissive source schema or field/type
coercion is added. Any writer repair requires a separate reviewed change.

All three JSON fields materialize as nullable VARCHAR holding EXACT retained JSON TEXT,
never parsed/normalized JSON columns. Whitespace, duplicate nested keys, unknown flags,
null/empty-array/empty-object distinctions and legacy serialization remain exact. SQL NULL
is not JSON null. Stored status READY or risk/allowed contents never authorize the platform.
The accepted source model's is_usable behavior is not native governance authority.

Four DATE fields materialize as nullable DATE labels, never UTC-midnight timestamps or
inferred exchange/session/knowledge boundaries. Created_at materializes as a nullable aware
TIMESTAMPTZ observation. Dates and creation clocks are never swapped or conflated with
import/recording clocks. Reversed date endpoints retain accepted structural flags, not
repairs or training-causality claims. Every field is recomputed from complete source bytes
on read, rejecting SQL scalar drift even when record bytes/hash remain unchanged.

Classification remains RETAINED_LEGACY_POLICY_OUTPUT_NOT_AUTHORIZED. Native policy
recomputation, JSON interpretation, policy authorization and training causality remain
false. Canonical identity/original availability/economic-validity instants remain null;
publication/decision eligibility remain false. Overwritten history is not recovered.

## APIs and synthetic workflow

Import nse_quant.data_platform.legacy_regime_policy_silver_store.

1. Construct PolicyBronzePins(source_label, layout_id, snapshot_id, capture_event_id,
   envelope_hash, recording_fingerprint) from actual reviewed native Bronze evidence.
2. Open native Bronze read-only. Silver production never probes current legacy SQL.
3. Explicitly initialize a separate empty dedicated file-backed target with
   initialize_regime_policy_silver(target). Existing/foreign/partial stores refuse; no
   automatic repair/adoption. Current catalog itself must be file-backed, not memory with
   a file attached. Caller owns connections, supplies no outer transaction and serializes
   writers. No multi-writer coordination is asserted.
4. Call observe_regime_policy_bronze(bronze, pins=pins), review full context hash, then
   persist_regime_policy_silver(bronze, target, pins=pins,
   expected_context_sha256=..., actor_id=..., code_revision=...).
5. Retain/review returned revision_id and recording_fingerprint separately. Receipt also
   includes row_count, job_id and decision_eligibility_asserted=false.
6. Close writer owners BEFORE read-only reopen. Use read_regime_policy_silver(
   readonly_silver, revision_id=..., expected_recording_fingerprint=...) for retained replay.
7. Use revalidate_regime_policy_silver(readonly_bronze, readonly_silver,
   revision_id=..., expected_recording_fingerprint=...) to add current native upstream equality.

The real silver.duckdb catalog/silver schema collision is preserved and tested, not renamed.
All new mutations/assertions quote actual catalog.schema.table. Same-live-file aliases use
separate cursor handles, reject without closing parents and retain owners. Code revision
is supplied as an exact full 40-character declaration; no full hash is invented from short
hashes or asserted to authenticate Git/interpreter/build/issuer roots.

## Scope, atomic persistence and original obligations

First-write scope = profile + source label + source snapshot ID + capture-event ID.
Layout/envelope/recording review pins, context-review hash, actor/revision labels and clocks
are excluded. Wrong reviewed layout fails under an original audited scope; changing layout
or recording pins cannot heal that SAME failed scope. A genuinely new source artifact is
a new revision scope, not recovery. Label renaming does not prove source namespace authority.

Prior scoped jobs/sets/attempt links block repeats. Orphan rows for the capture event block
adoption even after set/link/job removal. No implicit repair, retry-adoption, recovery or
orphan healing API exists. Original Bronze obligations are independently verified through
its actual pinned reader. Partial initialization is never silently adopted.

Native AuditLedger job precedes actual source observation. Full context/set, every full
projection, layout and all eleven scalar indices and attempt link commit atomically in
ONE domain transaction. A fault on the second observation INSERT rolls back partial domain
writes while FAILED audit remains. Final audit SUCCEEDED is separate from domain commit;
its failure leaves committed data unreadable and non-adoptable.

## Retained versus current native versus current legacy checks

read_regime_policy_silver validates read-only dedicated storage, exact reviewed revision/
recording pins, supported definitions/contract, full snapshot/context, source layout/schema,
projection bytes, all scalar indices, ordinal coverage/source links, revision identity,
attempt link and original single scoped job with exact PLANNED/RUNNING/SUCCEEDED history.
Missing/extra/reordered/altered/orphan data rejects.

Recording fingerprint binds selected context/set/observation metadata, source layout,
all scalar indices, source/context hashes, original jobs/events/links and clocks. DATE
indices serialize as ISO DATE labels; nullable aware source created_at and recording
clocks use astimezone(UTC) semantics, never replace(tzinfo=UTC). No DATE is passed to the
aware-clock serializer. Registration clocks are not independent time truth.

Offline replay proves retained content, NOT authentic declared Bronze pins or original
provider bytes. Retained Silver deliberately does not probe Bronze or legacy SQL and can
read after Bronze is missing or its audit no longer validates.

revalidate_regime_policy_silver requires TWO repeated actual pinned native Bronze
observations equal to frozen full context, bracketed by pinned Silver reads. Changed or
corrupt original Bronze audit fails this check while retained Silver may still replay.
Current legacy SQL equality remains the accepted Bronze revalidate_regime_policy_source
check, not a claim made by Silver revalidation. Tests exercise these distinctions.
Sequential observations are NOT atomic cross-database snapshots or source-file hashes.
Only supported stages actually run are replayed; no policy/strategy/risk/execution is run.

Definitions bind supported codec/source definitions and native DatasetContract, not
whole-repository code hashes, authenticated environments/interpreters/issuer authority,
environment recovery or silent reinterpretation of changed definitions.

## Independent bounds and transfer preflights

Accepted source bounds unchanged: 1..1000 rows; six text/JSON cells <=65536 UTF-8 bytes;
full snapshot <=1048576 bytes; projection <=524288 bytes and <=4194304 aggregate.
Full hex-snapshot context <=2200000 bytes; hex <=2097152 characters checked BEFORE decode,
then strict reconstruction rejects casing/whitespace aliases, extra keys or source mismatch.

Materialized source-variable-width scalar aggregate <=1048576 bytes independently.
Source_layout_id has a separate <=32-byte guard and known-ID reconstruction; its repeated
index is not used to inflate or shrink the source scalar aggregate contract. Count bounds
independently bound that repeated index. SQL preflights count, aggregate/max record bytes,
source scalar aggregate and EVERY text-cell/ID overflow in one transaction BEFORE row
transfer. Independent CASE guards remain on scalars, layouts, record bytes and IDs.
Oversized values in formerly NULL fields reject before a CASE can mask them as NULL.

Definitions/contracts/context/metadata and bounded catalog-name inventories have independent
SQL guards and small row limits. Accepted bounded metadata <=32768 serialized bytes per
query remains. Resource overflow rejects the entire recording, not selected observations.
These are content/transfer bounds, not SQL scan-cost, allocator/process-memory, hostile-file
safety or concurrency guarantees. No paging, partial success or accepted-limit inflation.

## Native tests and honest independent verification

Delivered repository tests import actual accepted policy codec/Bronze producer/readers,
AuditLedger/BronzeEventStore, RegimePolicy, DuckDBStore and new Silver code. Positive chains
cover BOTH physical layouts: real legacy writer on its matching appended layout; named
synthetic SQL on fresh layout; actual native Bronze; persisted Silver; owner closure and
read-only reopen. All eleven fields, per-row layouts, DATE/clock separation, JSON/NULL,
source READY and false native authority/eligibility flags are reconciled.

Tests cover mutation of EACH source scalar; materialized layout; frozen physical schema/
pin layout mismatch; full bytes/coverage/context/record/aggregate/nullable-mask faults;
layout non-healing; current-native vs current-legacy vs retained checks; original jobs,
contracts/definitions/orphans; aliases/init; hex predecode; independent scalar aggregate;
missing Bronze; partial SQL rollback; final-audit failure; maximum-text native persistence
with full payload and SHORT ID; and second actual observation then injected drift.
Drift/maximum-status SQL replacements are negative/boundary inputs, not authentic newly
trained policies or changed-source evidence. PYTEST_CURRENT_TEST is never cleared.

Assistant-executed checks, isolated Python 3.12.8 / DuckDB 1.2.2:
- New implementation/test syntax compiled; line lengths/trailing whitespace checked.
- 54 actual SQL/materializer probes passed across BOTH layouts: full roundtrip/revalidation,
  mutation of every source field (22 mutations total), materialized layout, bytes/coverage/
  clocks/link/audit faults, oversized context/record/nullable scalar, independent scalar
  aggregate, reviewed-context/layout scope non-healing, partial second-INSERT rollback,
  and maximum text/JSON roundtrips. Bronze/audit/contract boundaries were substituted;
  codec/helpers manually transcribed. These are NOT actual accepted-dependency native
  integration, actual legacy model/writer execution, repository QA or native E2E.
- ZIP exact three-member set, uniqueness, CRC, nonempty payloads and byte equality checked.

NOT run: Windows/uv interpreter verification; actual accepted-dependency native chain;
repository focused/data-platform/full pytest; Ruff; mypy; git diff --check; Git untracked
whitespace checks. These are NEW-package verification gaps, not pending 8489d2f/ce4bd29 QA.
Acceptance uses uv/configured tests/lint/types and tracked/untracked whitespace checks.
No substitute dependency code or external verification wrappers are delivered.

## Operational holds

This is retained policy Silver, not native policy training/application, legitimate governance
roots, independent identity/availability/economic evidence, eligible publication/admission,
complete strategy/portfolio inputs, native strategy/risk/execution, operational recovery,
real-data release or cutover. Legacy positional writer and numerical/research contracts
remain unchanged; no native platform completion percentage is claimed.
