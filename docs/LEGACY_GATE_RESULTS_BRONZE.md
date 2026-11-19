# Audited retained gate_results Bronze

## Scope and current baseline

This additive profile migrates the complete retained gate_results base table through
actual native Bronze/AuditLedger, with exact source-linked in-memory observations and
original-recording replay. It is not persisted gate Silver, original gate execution
replay, native strategy approval, admission, publication or consumer cutover.

Latest user-confirmed baseline: 8109556 at supplied matching local HEAD/origin, preceded
by fc3f714, with QA/tests passed CLOSED. No independently inspected Git/worktree/full
hash, repository/Windows/uv execution, commit or push is claimed. Historical delivery
statements do not reopen accepted QA. Accepted decision-evidence/evidence-snapshot
Silver and all other families are unchanged.

Access discovery returned no repository/filesystem/execution connector. Current source
inspection found underlying-IV Bronze AND Silver already present; neither is rebuilt.
No QA/commit attribution for those files beyond supplied evidence is invented.

Only disposable synthetic fixtures are authorized. Real-data loading/migration,
production publication, identity/key/policy/authority registration, trading and cutover
remain HELD. No native strategy/risk/broker/execution producer is called.

## Inspected actual source schema and writer methods

Actual persistence/duckdb_store.py DDL defines these ordered fields:

    gate_result_id VARCHAR PRIMARY KEY
    ts TIMESTAMPTZ
    run_id VARCHAR
    proposal_id VARCHAR
    strategy VARCHAR
    gate VARCHAR
    passed BOOLEAN
    reason VARCHAR
    details JSON

Only gate_result_id is a required key in this profile. All other cells remain nullable.
There is NO invented natural key over run/proposal/strategy/gate/time: identical nonkey
values under different IDs are retained, not deduplicated or joined. Full duplicate
primary IDs reject the complete capture, even if a malformed source lacks constraints.
Canonical encoded primary-ID ordering is deterministic, not causal/chronological order.
Empty stored labels are not rewritten into authenticated identities.

Two complete actual writer methods were retrieved and used by the supplied native tests:
write_feature_gate_result and write_feature_availability_result. Both INSERT OR REPLACE
nine values by retained ID. The first stores proposal_id=None, strategy=spot_feature_gate,
gate=spot_features, passed, json.dumps(reasons), json.dumps(checks). The second stores
feature_availability labels and json.dumps(checks, default=str). Its reasons remain TEXT.
Their symbol argument is not a materialized symbol column and cannot be recovered here.
No uninspected writer method or total writer coverage is claimed.

Actual-writer tests call the first method twice for the same ID and compare the retained
replacement with raw SQL, then call the second. Additional explicitly SQL-seeded rows
exercise nullable values, duplicate-key JSON and repeated nonkey fields. Those SQL
boundaries are not writer/plugin execution or authentic historical authorization.
INSERT OR REPLACE does not recover overwritten previous results.

Only the entire exact-schema main.gate_results BASE TABLE is accepted. No views,
selected/date-filtered rows, extra columns, naive TIMESTAMP, INTEGER booleans or VARCHAR
details substitutions are adopted. No generic cross-family schema adapter is introduced.

## Versions and retained semantics

Codec: legacy-gate-results-snapshot@1.
Projection: legacy-gate-result-observation@1.
Recording: legacy-gate-results-bronze-recording@1.
Command: migrate.legacy_gate_results@1.
Native source: legacy_gate_results_table_snapshot, origin_kind=legacy_snapshot.

All nine fields are retained. Nullable ts is either unknown/null or an aware stored SQL
instant normalized with astimezone(UTC). Naive source instants reject. Original timezone
labels, caller spellings/folds, independent availability, market time, economic validity
and discarded history are NOT recovered. Import receipt/native audit clocks are separate
aware observations; imported_at never becomes original gate availability. exchange_ts=None.

passed is exact stored True, False or None. Encoded integers/strings are not accepted as
booleans. SQL may already have coerced original caller input; that lost representation
is not recovered. True is retained true, not silently overwritten to false. Separate
native approval/eligibility assertions are false. A legacy passed=True is not independent
proof of actual gate execution, authenticated safety or permission to trade.

reason is exact nullable opaque TEXT: it may contain JSON text from a writer, ordinary
text, invalid JSON, whitespace or claims. It is never parsed as a reason list.
details is exact nullable source CAST(JSON AS VARCHAR) text. Retained whitespace,
duplicate keys, scalar/array/object forms, JSON null and embedded eligible/passed claims
are not interpreted, normalized, extracted or independently syntax-revalidated.
SQL NULL is None, distinct from JSON literal null text "null" and empty text.

The pure constructor accepts opaque details text as a CONTENT boundary; it does not
attest that arbitrary bytes came from a real JSON column. Actual native source capture
checks the actual source JSON type. It does not bypass SQL JSON validation. Outer
snapshot/record JSON is independently strict/canonical, with duplicate/unknown structure
and nonfinite literals rejected. No original provider/plugin payload bytes are recovered.

Classification: RETAINED_LEGACY_GATE_RESULT_NOT_NATIVE_APPROVAL.
Each observation binds complete stored fields, primary key, source label, full snapshot,
capture-event/envelope pins and every source ordinal. Original gate/native decision
replay, details/reason interpretation, provider/history recovery, verified availability/
economic validity, publication and decision eligibility remain false. Canonical identity
and original_availability_at remain null. No proposal/strategy ID binding is invented.

## Actual native producer/read path

legacy_gate_results_bronze.py:

- capture_gate_results(readonly_legacy, source_label=...)
- preserve_gate_results(readonly_legacy, initialized_bronze, source_label=...,
  expected_snapshot_id=..., imported_at=..., actor_id=..., code_revision=...)
- read_recording_bytes(bronze, source_label=..., snapshot_id=..., capture_event_id=...,
  envelope_hash=...): lower-level verifier; not a public readonly/review-pin substitute.
- read_gate_results_bronze(readonly_bronze, source_label=..., snapshot_id=...,
  capture_event_id=..., envelope_hash=..., expected_recording_fingerprint=...)
- revalidate_gate_results_source(readonly_legacy, readonly_bronze, **public_reader_pins)

One source transaction covers exact schema/base-table observation, SQL count/aggregate/
max-text preflight, independent CASE guards on every transferred text/JSON column and
max+1 row transfer. Complete nullable boolean/instant/key/artifact validation follows.
No caller-successful result/DTO or filtered prefix is imported as source proof.

Two actual complete captures must agree with the reviewed content pin and each other.
Every projected-record resource check occurs BEFORE actual native append_batch. Actual
BronzeEventStore/AuditLedger retain one event, complete artifact and batch in a domain
transaction. Exactly one variant must be inserted; retry/conflict/already-committed reuse
rejects. Initialize NEW native targets explicitly with accepted initialization APIs.
Code revision is a supplied full lower-case 40-hex execution declaration, not an invented
expansion of a short user hash or authenticated code/interpreter/issuer attestation.

First-write scope is profile+source label, excluding content/recording/review pins,
import clock and actor/revision labels. Original scoped jobs, events, batches or retained
reviewed artifact block reuse before capture. A new label is a new declaration, not
legitimate namespace authority or recovery. Caller serializes ownership; no shared
writers or outer transactions. Successful retry/adoption/cleanup is deliberately absent.

Retained reading verifies stored event/envelope IDs, full snapshot/artifact, native
variant scope/job coverage, original batch counts/fingerprint/sequence, original scoped
job/config/scope, and exact PLANNED/RUNNING/SUCCEEDED history. Original-job batch/artifact
variants cannot hide behind a good matching subset. A separately reviewed recording
fingerprint binds selected recording/audit metadata and clocks, not just content.
Hash consistency/application audit integrity is not independent source authentication,
DB permissions or a signed root against rewriting storage and supplying new trusted pins.

Domain append and final audit SUCCEEDED are separate. Append failure rolls artifact/
event/batch rows back but retains original failed audit obligation. Committed content
without original final success cannot be read as valid or adopted. Deleting audits,
changing pins/actor/clock or retrying does not heal it. Source SQL/operational errors
propagate, not policy acceptance, unavailable business outcomes or fabricated refusals.

Current-source revalidation adds two complete actual present SQL equality observations
bracketed by pinned native reads. Retained Bronze can still replay when current legacy
SQL has changed. Sequential observations are not atomic multi-resource snapshots,
source-file hashes or original plugin/gate/decision execution replay.

Owners close before readonly reopen; source-target live-file cursor aliases reject
without closing parent owners. New mutations/assertions quote actual catalog.schema.table.
Public readers enforce actual readonly mode. No production registration is performed.

## Independent bounds

Existing family limits are unchanged.

- 1..1000 complete rows, SQL count preflight and max+1 guard.
- Every retained text/JSON cell <=65536 UTF-8 bytes, nullable fields accounted separately.
- Aggregate text transfer <=1048576 bytes before transfer.
- Canonical whole snapshot <=1048576 bytes independently of raw transferred text.
- Full projected records <=524288 bytes each and <=4194304 aggregate, before append.
- Native envelope <=8192 bytes; independently row-bounded metadata queries <=32768
  serialized bytes through actual common helpers, with SQL CASE-guarded identifiers.

Escaping can exhaust snapshot/projection budgets even when SQL text preflight fits.
Complete operation rejects; no limit inflation, partial success, paging, approximation
or unbounded export. Bounds are not scan-cost, peak-memory, external concurrency or
hostile-database-file safety promises. Resource pytest parameters retain full payloads
with explicit SHORT IDs, never modified PYTEST_CURRENT_TEST.

## Tests and honest verification

Pure tests cover exact nullable booleans, all nonkey NULLs, unique primary ID without
invented natural keys, opaque reason/details, SQL NULL/JSON-null distinctions, aware/
naive/UTC contracts, canonical ordering, outer schema/checksum/duplicate-key refusal,
text/count/raw-byte and independent projection bounds. Pure opaque invalid JSON does
not attest an actual source JSON column.

Native tests invoke actual retrieved legacy writer methods, actual native AuditLedger/
BronzeEventStore and the new producer/retained/current-source readers. Raw SQL/codec
values are the oracle, not a guessed serialized replacement. Coverage includes same-ID
retained replacement, nullable SQL boundaries, repeated nonkey rows, all fields, original
recording corruption, failed review scope, extra jobs, current-source distinction,
post-commit final audit, timezones and same-live-file aliases. Append rollback test uses
an explicit failing execute proxy at the actual variant INSERT boundary, NOT an alleged
independent DuckDB constraint failure or successful source substitute.

Repository-dependent native tests are supplied, NOT assistant-executed unless explicitly
reported otherwise. Pure tests and isolated actual capture SQL, when executed, have
separate attribution in the delivery response. Helper transcriptions/placeholders are
not native producer/reader E2E and are not delivered as accepted-module replacements.
Syntax/line length/whitespace and ZIP exact unique members/nonempty/CRC/payload equality
are checked before delivery, not conflated with Windows/uv, Ruff/mypy/full QA or acceptance.

## Delivery, holds and new-work checks

Copy absent additions only; STOP/compare if a destination exists. No accepted modules,
QA repairs, pyproject/lock, runtime logs or scripts/qa are replaced. Preserve
logs/live_status.json. No PowerShell QA runner, per-payload SHA256 manifest or standalone
ZIP verifier is included. Distributed pytest dependency work remains unchanged; this
package does not certify full-suite parallel safety/performance.

    uv run python -c "import sys; print(sys.executable); print(sys.version)"
    uv run pytest tests/data_platform/test_legacy_gate_results.py -q
    uv run pytest tests/data_platform/test_legacy_gate_results_bronze.py -q
    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Check untracked additions for whitespace too. Earlier user-confirmed QA through 8109556
stays CLOSED. This package is not persisted gate-results Silver or original gate replay;
no original availability/economic validity, native eligibility or hold release is claimed.
