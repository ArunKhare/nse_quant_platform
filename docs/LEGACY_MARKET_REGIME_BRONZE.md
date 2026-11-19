# Audited retained market-regime Bronze preservation

## Accepted baseline and additive scope

User-confirmed spot Silver QA/test baseline 165f89b remains CLOSED. Reported HEAD is
feat/medallion-feature-store at 165f89b; reported origin remains 0c515de. No push or
independent Git/worktree/Windows execution is claimed. Historical "not run" delivery
attribution does not reopen accepted QA.

Access was rechecked: no repository/filesystem/execution connector was returned.
Project Sources are retrieval, not an executable checkout. Targeted retrieval recovered
actual current spot Silver source plus actual market_regimes schema/write/as-of-read
interfaces. Requested evidence_snapshots writer was not recovered. That is a retrieval
limitation, NOT evidence of absence/staleness. Its schema alone was insufficient to select
that family; the separately retrieved write_decision_evidence method is NOT its writer.
No evidence-snapshot or naive decision_evidence timestamp migration is claimed here.

This bounded chunk implements a separate retained market_regimes SQL migration contract,
actual native Bronze/AuditLedger production, exact source-linked IN-MEMORY observations,
original-recording replay, adversarial/native integration tests and documentation. It is
not persisted regime Silver, native regime recomputation, Gold, policy authorization,
publication/admission, recovery or cutover.

Archive contains only:
- src/nse_quant/data_platform/legacy_market_regimes.py
- src/nse_quant/data_platform/legacy_market_regime_bronze.py
- tests/data_platform/test_legacy_market_regime_bronze.py
- docs/LEGACY_MARKET_REGIME_BRONZE.md

Copy absent additions only. STOP and compare if a destination exists. Accepted dependencies
are imported unchanged, never replacement payloads. Do not modify logs/live_status.json,
recreate scripts/qa, add a QA runner/manifest/standalone ZIP verifier, infer real-data
release or cut over the legacy loop. No native analytical detour is included.

## Actual inspected schema and source semantics

persistence/duckdb_store.py defines exactly:
symbol VARCHAR, ts TIMESTAMPTZ, trend_regime VARCHAR, volatility_regime VARCHAR,
iv_regime VARCHAR, regime VARCHAR, features JSON; PRIMARY KEY(symbol, ts).
The key columns must be known; remaining columns can retain SQL NULL.

write_market_regime is an actual keyword-only writer taking symbol, ts, four labels and
features dict, issuing INSERT OR REPLACE and json.dumps(features, default=str). Distinct
textual timezone representations of the same stored instant can replace the same key.
Overwritten labels, feature payloads, original receipts and history are unrecoverable from
remaining rows. No original provider HTTP/WS artifacts are recovered by serializing SQL.

get_market_regime_as_of queries symbol and ts <= supplied ts, takes the latest retained
row and parses features. That legacy as-of query is not an independent publication/
knowledge-cutoff/availability guarantee. This migration does NOT call the parsing reader:
it would erase original JSON spelling and duplicate-key information. No legitimacy or
native eligibility is inferred from regime names, keys, feature metadata or clock alignment.

## New contracts and exact observation meaning

Snapshot: legacy-market-regime-snapshot@1.
Projection: legacy-market-regime-observation@1.
Native Bronze recording: legacy-market-regime-bronze-recording@1.
Command: migrate.legacy_market_regimes@1.
Native source: legacy_market_regime_table_snapshot; origin_kind=legacy_snapshot.

Only the complete exact ordered-schema BASE TABLE is supported, not views/filters/
alternative types/partial captures/hidden paging/arbitrary tables. Actual non-null key
presence/uniqueness is checked independently of source SQL constraints; the artifact does
not independently attest source constraint declarations.

Every stored text label remains exact, including unrecognized labels, whitespace and
Unicode. Empty/whitespace/missing labels are flagged structurally, not repaired or promoted
to canonical native enums. Stored ts normalizes via astimezone(UTC), never replace(tzinfo=UTC).
Naive encoded instants reject. Equivalent clock spellings cannot create duplicate winners.

features remains EXACT STORED JSON TEXT, never parsed/reformatted/reordered/interpreted.
Unknown and duplicate nested keys, numeric/string spelling and whitespace remain retained.
SQL NULL, JSON text null and JSON text {} remain three distinct observations. An embedded
eligible/authorized/available flag is not trusted. Pure codec replay preserves opaque text;
it does not independently attest DuckDB JSON syntax, original SQL capture or provider truth.
Outer artifact JSON is a separate strict canonical contract that rejects duplicate and
unknown structural fields. These two JSON semantics are intentionally distinct.

Each projection retains all seven fields, complete source snapshot/capture-event/envelope
pins and deterministic source ordinal in canonical encoded-key order. Classification is
RETAINED_LEGACY_REGIME_OUTPUT_NOT_RECOMPUTED. features_interpreted,
native_regime_recomputed and policy_authorized remain false. Identity, original availability
and economic-validity instants remain null; publication and decision eligibility remain
false. These rows are not governed regime-policy decisions or complete strategy inputs.

## Actual native capture and preservation

capture_market_regimes(readonly_legacy, source_label=...) owns a single SQL transaction.
Source must be read-only, caller-owned and without an outer transaction. Exact schema/type,
row count, aggregate UTF-8 text and individual cell-byte preflights precede transfer.
Nullable columns are counted independently with COALESCE, so NULL in features cannot hide
large label fields. Independent SQL CASE guards remain on every text/JSON cell.

preserve_market_regimes(readonly_legacy, initialized_bronze, source_label=...,
expected_snapshot_id=..., imported_at=..., actor_id=..., code_revision=...)
requires separate resources and an initialized dedicated file-backed current native Bronze
catalog. Initialize NEW targets explicitly using actual AuditLedger.initialize and
BronzeEventStore.initialize. Producer/readers do not initialize, adopt or repair targets.

Two actual complete SQL captures must agree with the reviewed pin. Complete snapshot and
projection reconstruction/resource checks occur BEFORE append. If the artifact fits but
a projection overflows its independent bound, the whole audited attempt fails before
native data append; no successful unreadable public-reader receipt is fabricated.
Actual native append_batch retains one event and the full artifact and must create
exactly one new variant, without retry/conflict reuse.

Import time is a supplied import receipt observation, never recovered original provider
receipt/availability. Native exchange_ts is not fabricated from retained ts. Supplied
code revision must be a full lower-case 40-character declaration; no full Git hash is
invented from user-supplied short hashes. Labels/runtime observations are not independently
authenticated source/interpreter/build/issuer/namespace governance roots.

First-write scope = profile + source label. Reviewed snapshot/recording pins, actor/revision
labels and clocks are excluded. Original scoped jobs, variants, batches or a pre-existing
reviewed artifact block adoption/reuse. Changing excluded fields cannot heal failed scope.
A new label is a new declaration, not recovery of previous obligations or source authority.
Caller serializes writes; no external multi-writer coordination is promised.

Receipt contains source_label, snapshot_id, capture_event_id, envelope_hash,
recording_fingerprint, row_count, job_id and false decision_eligibility_asserted.

## Original recording versus current source equality

read_recording_bytes(bronze, source_label=..., snapshot_id=..., capture_event_id=...,
envelope_hash=...) is an explicit lower-level original-recording verifier returning full
snapshot bytes plus observed fingerprint. Public reading additionally requires read-only
ownership and a separately reviewed recording fingerprint; the low-level API is not a
substitute for those requirements.

read_market_regime_bronze(readonly_bronze, source_label=..., snapshot_id=...,
capture_event_id=..., envelope_hash=..., expected_recording_fingerprint=...)
checks persisted event AND envelope IDs, exact envelope/payload reconstruction, complete
artifact, native batch fingerprint/counts/sequence, original single scoped job and exact
PLANNED/RUNNING/SUCCEEDED history. The separately reviewed recording fingerprint binds
selected clocks/metadata/audit lineage independently of the content hash. Hash equality
alone is not original audit, source authenticity or strategy/policy replay.

revalidate_market_regime_source(readonly_legacy, readonly_bronze, **public_reader_pins)
adds two actual current whole-table SQL equality observations, bracketed by pinned native
reads. Retained native replay can succeed when current legacy SQL differs or is unavailable.
Sequential observations are NOT atomic cross-database snapshots or source-file-byte hashes.
Only the capture/verification/projection stages actually run are represented; no native
strategy, portfolio risk, policy application, loop or execution replay is asserted.

Native append/domain commit and final audit SUCCEEDED are separate obligations. A SQL
insert failure rolls back artifact/event/batch writes while retaining a failed job.
Failure of final SUCCEEDED after domain commit leaves original data unreadable and
non-adoptable. Deleting original audits does not authorize orphan adoption. No implicit
retry, recovery, repair or hold release API is included.

Writer owners close BEFORE read-only reopen. Same-live-file aliases use distinct cursor
handles, reject without closing the parent, and are not renamed to hide collisions.
All new mutations and test assertions quote actual catalog.schema.table identifiers.

## Independent resource bounds

These are new reviewed regime-family bounds, not inflation of prior contracts:
- 1..1000 complete rows, count preflight and max+1 transfer guard.
- Each of six text/JSON cells <=65536 UTF-8 bytes.
- Aggregate transferred raw text <=1048576 bytes, independently counting every nullable cell.
- Complete canonical snapshot <=1048576 bytes INDEPENDENTLY of raw text bytes.
- Each projection <=524288 bytes; aggregate projected records <=4194304 bytes.
- Encoded clock <=64 characters with exact canonical aware UTC spelling.
- Envelope transfer <=8192 bytes; inherited bounded native metadata <=32768 serialized
  bytes per query with independent small row limits and SQL CASE guards before transfer.

Canonical escaping can make an otherwise bounded raw-text row exceed snapshot/projection
limits; whole capture/attempt rejects, not partial observations. The raw decoder checks
bytes before strict JSON parsing. Bounds constrain content and transfers, not SQL scan
cost, allocator/process memory, hostile on-disk safety or external concurrency.

## Tests and honest verification attribution

Delivered tests import actual DuckDBStore.write_market_regime, AuditLedger,
BronzeEventStore and new codec/native producer/readers. The positive fixture uses the real
legacy writer, proves offset-equivalent replacement, retains arbitrary labels and default=str
output, injects an opaque duplicate-key JSON boundary through actual retained SQL, and adds
a nullable retained row. It then captures/preserves native Bronze, closes writers and
reopens read-only readers, reconciling every field and false eligibility/authority flags.
The injected JSON is boundary testing, not authentic authorization evidence.

Other tests cover current SQL versus retained replay; all original event/envelope/payload/
artifact/audit/clock tampering; reviewed-pin non-healing; schema/view/naive/key/count
rejection; UTF-8/text bounds; SQL rollback; final-audit failure; aliases; original orphans;
strict outer JSON; NULL vs JSON null vs {}; and projection overflow before native append.
Drift changes returned bytes AFTER an actual second capture; it is a negative-boundary
injection, not authentic concurrent-source evidence. Large parameters retain full payloads
and assertions with SHORT pytest IDs; PYTEST_CURRENT_TEST is never cleared.

Assistant-executed, isolated Python 3.12.8 / DuckDB 1.2.2:
- New implementation/tests compile; line-length and trailing-whitespace checks pass.
- 28 actual SQL capture/projection cases pass: every text column's cell bound, UTF-8
  boundaries, nullable fields/JSON null/duplicate nested keys, schema/view/naive/key/count
  rejection, aggregate text, independent canonical snapshot bound and projection bound.
  Strict JSON/clock/catalog helpers were manually transcribed. Audit/Bronze imports were
  deliberately unavailable and would raise if exercised. These are NOT actual native
  producer/reader integration, real legacy-writer execution or repository/native E2E QA.
- ZIP exact four-member set, uniqueness, CRC, nonempty payloads and payload-byte equality checked.

NOT run: actual accepted-dependency native chain, Windows/uv interpreter check, repository
focused/data-platform/full pytest, Ruff, mypy, git diff --check or Git untracked whitespace
checks. These are NEW-package verification gaps, not pending 165f89b baseline QA. Acceptance
uses uv and configured tests/lint/types plus tracked/untracked whitespace checks. No
transcribed dependencies/placeholders or external verification wrappers are delivered.

## Remaining operational holds

Persisted regime Silver remains next, not an implied completed stage. Evidence-snapshot,
policy and decision-evidence contracts require their own actual-source inspections.
No native regime/policy recomputation, authenticated identity/governance/availability,
positive PIT admission, complete native strategy/risk/execution, operational recovery,
real-data release, consumer cutover or completion percentage is claimed. Accepted numerical,
quote/window admission and legacy-loop implementations are unchanged.
