# Layout-explicit retained regime-policy Bronze preservation

## Accepted baseline, source access and additive scope

User confirmed the latest market-regime Silver package QA passed. Treat that package as
QA CLOSED even though no new commit was supplied. Last supplied Git pointer report was
HEAD/origin feat/medallion-feature-store at 1d528db; no newer hash/push/worktree state is
invented. Historical "not run" delivery attribution does not reopen accepted QA.

Access was rechecked; no repository/filesystem/execution connector was returned. Project
Sources are retrieval only, not an executable checkout. Targeted retrieval recovered
actual current regime Silver source/tests and actual regime_policies DDL, positional
save_regime_policy writer and research/regime_policy.py RegimePolicy domain. The policy
reader's date-filter query was recovered, not its complete tail; no unseen behavior or
full reader replay is claimed. Accepted source and QA repairs are not replaced.

This bounded implementation adds an explicit retained regime_policies snapshot contract,
actual native Bronze/AuditLedger preservation, exact source-linked IN-MEMORY observations,
original-recording replay, native integration/adversarial tests and documentation. It is
not persisted policy Silver, policy application, native training, Gold, authorization,
positive admission, recovery or cutover.

Archive members:
- src/nse_quant/data_platform/legacy_regime_policies.py
- src/nse_quant/data_platform/legacy_regime_policy_bronze.py
- tests/data_platform/test_legacy_regime_policy_bronze.py
- docs/LEGACY_REGIME_POLICY_BRONZE.md

Copy absent additions only. STOP and compare if any destination exists. Do not overwrite
accepted dependencies, modify logs/live_status.json, recreate scripts/qa, add a QA runner,
per-payload manifest or standalone ZIP verifier, infer real-data release or cut over loops.

## Consequential inspected layout mismatch: preserve, do not repair

Current inspected fresh DDL declares these 11 ordered columns:
policy_id VARCHAR PRIMARY KEY; symbol VARCHAR; train_start DATE; train_end DATE;
test_start DATE; test_end DATE; allowed_regimes JSON; regime_metrics JSON;
selection_status VARCHAR; risk_limits JSON; created_at TIMESTAMPTZ.

The same inspected _create_schema branch appends risk_limits when an existing table lacks
it. A reviewed created_at-before-risk_limits layout is therefore separately represented.
This is not a claim about the user's current retained database order; actual read-only
metadata MUST match an explicitly chosen reviewed layout at capture time.

Inspected save_regime_policy uses positional INSERT OR REPLACE. It serializes sorted
policy.allowed_regimes, regime_metrics with json.dumps(default=str), selection_status,
then datetime.now(UTC), THEN json.dumps(risk_limits or {}, default=str). That final order
matches created_at followed by risk_limits, NOT the inspected fresh DDL's final order.
No named-column repair, schema alteration, field swap, implicit type coercion or source
writer modification is included here. This new migration reads actual fields BY NAME.
A temporal-looking value in risk JSON is never promoted to created_at.

RegimePolicy is the actual source dataclass exposing allowed_regimes, regime_metrics and
selection_status. Its is_usable property checks selection_status == READY and allows uses
that source property plus membership. Those are legacy domain behaviors, NOT authenticated
native governance roots or permission. Production migration does not instantiate or apply
RegimePolicy, rerun training, select a strategy or trust stored risk/allowed/status data.

latest_regime_policy's inspected query filters symbol and test DATE interval using an
as_of date and orders by test_start. A DATE filter is not independent availability,
training-causality or valid-time evidence. The full reader was not retrieved and is not
replayed. Source selection_status and dates are retained rather than reinterpreted.

## Two explicit exact physical layouts, one named canonical row shape

Snapshot: legacy-regime-policy-snapshot@1.
Projection: legacy-regime-policy-observation@1.
Native recording: legacy-regime-policy-bronze-recording@1.
Command: migrate.legacy_regime_policies@1.
Native source: legacy_regime_policy_table_snapshot; origin_kind=legacy_snapshot.

Reviewed layout IDs are:
- risk-before-clock: the exact fresh DDL order above.
- clock-before-risk: identical first nine columns, then created_at TIMESTAMPTZ and
  risk_limits JSON. This explicitly models the append-risk layout, not a guessed repair.

Every capture requires layout_id. No auto-detection, permissive column reordering or
arbitrary layouts. The complete exact ordered names/types and BASE TABLE kind must match.
Missing/extra/duplicate/changed types, naive clock columns, partial snapshots and views
reject. Existing retained layouts without all 11 fields require another reviewed contract;
missing risk/created fields are not invented.

Rows use the canonical named order (risk_limits then created_at), and each artifact retains
layout_id AND exact physical_columns separately from canonical columns. Same named values
under different physical layouts produce DIFFERENT snapshot hashes. Replaying a forged
physical layout or silently switching the reviewed layout rejects. The mapping is a
source-linked named projection, not proof of what a historical writer originally intended.

Only policy_id must be known/unique. All other actual nullable cells remain NULL. Text
IDs, symbols/status and JSON remain opaque retained fields, not canonical identity.
allowed_regimes/regime_metrics/risk_limits retain EXACT stored JSON TEXT, including
whitespace, duplicate nested keys, null/empty spelling and legacy serialization. SQL NULL,
JSON text null, [] and {} are not normalized together. Pure codecs do not independently
attest source SQL JSON syntax or provider authenticity; outer artifact JSON is separately
strict/canonical and rejects duplicate/unknown structural fields.

DATEs stay DATE labels, never UTC midnight instants, inferred trading sessions, settlement
clocks or independent knowledge boundaries. Reversed retained train/test endpoints receive
structural flags, not repairs or native validity determinations. No training-causality,
window completeness, regime-metric validity, native risk bound or sufficient input claim.
created_at normalizes an actual aware stored instant via astimezone(UTC), never
replace(tzinfo=UTC); NULL stays unknown. It is not proof of original publication/availability.

Classification: RETAINED_LEGACY_POLICY_OUTPUT_NOT_AUTHORIZED. Full projections retain all
11 fields, source layout ID, snapshot/capture-event/envelope pins and exact ordinal.
policy_json_interpreted, native_policy_recomputed, policy_authorized and
training_causality_verified remain false. Identity/original availability/economic-validity
instants remain null; publication/decision eligibility remain false EVEN for source READY.
Overwritten policy history, original risk limits and original bytes cannot be recovered.

## Native capture, preservation and first-write obligations

capture_regime_policies(readonly_legacy, source_label=..., layout_id=...) owns one SQL
transaction, requires caller ownership/no outer transaction, validates exact reviewed
physical schema, preflights row count and aggregate/max text bytes before transfer, and
uses independently guarded named-column reads. Captures cover the ENTIRE retained table.
Actual policy key uniqueness is recomputed, not inferred from source constraint DDL.

preserve_regime_policies(readonly_legacy, initialized_bronze, source_label=..., layout_id=...,
expected_snapshot_id=..., imported_at=..., actor_id=..., code_revision=...)
requires separate resources and an initialized dedicated file-backed current Bronze
catalog. Initialize NEW targets explicitly with actual AuditLedger.initialize and
BronzeEventStore.initialize. Producer/readers never initialize, adopt or repair targets.

Two actual complete captures must agree with the reviewed pin. Full snapshot/projection
reconstruction and output resource checks occur BEFORE actual native append_batch, which
retains one event plus the complete artifact and must insert exactly one new variant.
Import time is a supplied import receipt observation, not original policy availability or
authenticated time. Native exchange_ts is not fabricated from stored created_at.

First-write scope = profile + source label. Layout/snapshot/recording review pins, actor/
code labels and clocks are excluded; changing them cannot heal the SAME failed scope.
In particular a wrong reviewed layout creates a failed audited attempt; changing layout
cannot adopt it. Original scoped jobs/variants/batches/reviewed artifacts block repeats.
A new label is a new declared scope, not recovery or legitimate namespace authority.
Caller serializes writers; no multi-writer coordination or recovery/adoption API exists.

Receipt: source_label, layout_id, snapshot_id, capture_event_id, envelope_hash,
recording_fingerprint, row_count, job_id, decision_eligibility_asserted=false. Code revision
must be a supplied full lower-case 40-character declaration; no full Git hash is invented
from supplied short hashes. Runtime/code labels are not authenticated issuer/build roots.

## Native original-recording reader and separate current SQL check

read_recording_bytes(bronze, source_label=..., layout_id=..., snapshot_id=...,
capture_event_id=..., envelope_hash=...) is an explicit lower-level original-recording
verifier returning full bytes and observed fingerprint. Public reading adds read-only
ownership and a separately reviewed recording fingerprint; low-level reading is not a
substitute for those requirements.

read_regime_policy_bronze(readonly_bronze, source_label=..., layout_id=..., snapshot_id=...,
capture_event_id=..., envelope_hash=..., expected_recording_fingerprint=...)
checks stored event/envelope IDs, full artifact/snapshot/envelope, reviewed layout, native
batch fingerprint/counts/sequence, single original scoped job and exact original
PLANNED/RUNNING/SUCCEEDED history. Job config binds layout plus full snapshot/definition.
Selected clocks/metadata/audit lineage are bound in the separate recording fingerprint.
Content replay/hash equality alone does not authenticate original SQL capture or audit.

revalidate_regime_policy_source(readonly_legacy, readonly_bronze, **public_reader_pins)
adds two current full-table equality observations under the SAME reviewed physical layout,
bracketed by pinned native reads. Retained native replay can succeed when current legacy
SQL differs or is unavailable. Sequential observations are NOT atomic cross-database
snapshots, source-file hashes or full policy/strategy/risk/execution replay.

Native append's domain commit and final audit SUCCEEDED are separate obligations. SQL
insert failure rolls back artifact/event/batch writes while retaining failed jobs. Missing
final SUCCEEDED after domain commit blocks original reading/adoption. Deleting original
audits cannot authorize orphan reuse. No healing, hold release or implicit recovery exists.

Owners close BEFORE read-only reopen. Same-file aliases use distinct cursor handles,
reject without closing parents and retain real owners. New mutations/assertions fully
quote actual catalog.schema.table names; no catalog renames hide collisions.

## Independent bounds

This new policy-family contract does not inflate any accepted profile:
- 1..1000 complete rows, count preflight plus max+1 transfer guard.
- Six text/JSON fields <=65536 UTF-8 bytes each; aggregate raw text <=1048576 bytes.
  Nullable columns are counted independently with COALESCE, never masking other bytes.
- Complete canonical snapshot <=1048576 bytes independently of raw-text preflight.
- Projection <=524288 bytes each and <=4194304 bytes aggregate.
- DATE spelling <=10 characters; aware stored clock <=64 characters and exact canonical UTC.
- Envelope <=8192 transferred bytes; accepted bounded metadata <=32768 serialized bytes
  per independently row-bounded query, with independent SQL CASE text guards.

Raw decoder bounds precede strict outer JSON parsing. Canonical escaping can independently
exhaust snapshot/projection bounds, rejecting the whole attempt before native data append.
No partial success, good-subset filtering, hidden paging or inflated exports. Bounds do
not guarantee scan cost, allocator/process memory, hostile-file safety or concurrency.

## Tests and honest verification attribution

Delivered tests use actual RegimePolicy and DuckDBStore.save_regime_policy on an explicitly
constructed clock-before-risk retained fixture, then actual native Bronze producer/readers.
This preserves the inspected append layout; it is not a silent fixture reorder hiding the
fresh-layout mismatch. The risk-before-clock positive fixture uses NAMED synthetic SQL,
NOT a repaired positional writer. Tests reconcile every field and physical layout, source
replacement, opaque JSON, SQL NULL/JSON null/empty list, and false native authority flags.

A separate actual-repository negative test checks the inspected fresh DDL and demonstrates
that its positional writer fails there without inserting a row. It does not reopen accepted
QA or modify the writer. If current source differs from retrieved source, compare that exact
boundary rather than overwriting repairs or claiming this package verified an unseen change.

Other tests cover wrong layout/no healing, original event/payload/artifact/audit/clock/layout
pins, current SQL vs retained replay, text/row bounds, SQL rollback/final audit, strict outer
JSON, duplicate keys, alias ownership, naive clock rejection, reversed date labels, physical
schema hash binding, orphans and drift after a real second capture. Drift is a deliberate
negative boundary, not authentic concurrent-source evidence. Full large payloads use SHORT IDs.

Assistant execution, isolated Python 3.12.8 / DuckDB 1.2.2:
- New implementation/tests compile; line lengths/trailing whitespace checked.
- 48 actual SQL capture/projection cases passed across BOTH explicit layouts: every text
  field's individual limit/overflow, UTF-8, schema/naive/null key/duplicate/empty/row limits,
  canonical snapshot overflow, projection bound, nullable cells and named risk/clock mapping.
  Shared strict JSON/clock/catalog helpers were manually transcribed. Native Audit/Bronze
  imports deliberately raise if exercised and were NOT exercised. These are NOT native
  producer/reader integration, actual legacy-writer/model execution or repository E2E/QA.
- Two separate positional-SQL probes (transcribed inspected writer arguments, ACTUAL PK
  shape) confirmed fresh risk-before-clock raises ConversionException without rows, while
  clock-before-risk stores named clock/risk values correctly. Initial isolated probe omitted
  its PK and hit a binder error; it was corrected and BOTH effects rechecked. This is not
  Windows or actual repository writer execution.
- ZIP exact four-member set, uniqueness, CRC, nonempty payloads and byte equality verified.

NOT run: actual accepted-dependency native chain, Windows/uv interpreter check, repository
focused/data-platform/full pytest, Ruff, mypy, git diff --check or Git untracked whitespace
checks. These are NEW-package verification gaps, not pending latest regime Silver QA.
Acceptance uses uv/configured tests/lint/types and tracked/untracked whitespace checks;
no substituted dependencies or verification runners are delivered.

## Remaining operational holds

Persisted source-linked policy Silver remains next. No native policy training/application,
authenticated governance/identity/availability, positive PIT admission, complete strategy/
portfolio inputs, native strategy/risk/execution, recovery, real-data release, cutover or
completion percentage is claimed. Accepted solvers and legacy/research-only consumers stay
unchanged. A separate reviewed task is required for any legacy positional-writer repair.
