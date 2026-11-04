# Bounded native preservation of legacy market tables @1

## Scope and evidence

This additive implementation uses the actual inspected BronzeEvent/BronzeEventStore
and AuditLedger APIs. Schema definitions were reconciled with the supplied
outputs/legacy-database-schema.json and legacy duckdb_store.py definitions.
Existing production files, accepted input/risk work, decoder and fixtures are unchanged.

This is a bounded migration PRESERVATION slice, not whole-database migration,
provider-frame reconstruction, eligible publication or strategy cutover. It targets
an entire explicitly selected main.option_stream (22 columns) or main.spot_candles
(10 columns). Caller supplies a reviewed source label and exact snapshot SHA-256.
Unknown columns, changed types, views, duplicate/unknown keys, empty/oversized tables
and invalid supported values reject the whole table. There is no partial promotion.

No user data was migrated. Real-data loading/migration/backfill remains HELD.
Synthetic fixtures are allowed. There is no CLI or force/allow-unknown switch.

## APIs

    capture_legacy_table(source, table=..., source_label=...) -> LegacySnapshot
    replay_legacy_snapshot(payload, expected_snapshot_id=...) -> document
    typed_legacy_observations(payload, expected_snapshot_id=...) -> observations
    preserve_legacy_snapshot(source, bronze, table=..., source_label=...,
        expected_snapshot_id=..., imported_at=..., actor_id=..., code_revision=...)
    read_preserved_legacy_snapshot(bronze, capture_event_id=..., envelope_hash=...,
        expected_snapshot_id=...) -> observations

Caller owns connections, without outer transactions. Capture requires actual
read-only DuckDB source. Native persistence requires an already initialized,
separate file-backed Bronze/audit target. Initialization is not performed implicitly.
Do not construct legacy DuckDBStore to inspect a source: writable construction may
initialize legacy schema. Do not run the dormant historical_importer as this path.

## Stored-value contract

All supported cells retain a type through the exact pinned schema. NULL remains
NULL; zero remains zero. Finite DOUBLE values are represented by float.hex(),
including signed zero: these are exact stored binary64 values, NOT reconstructed
original decimal quotes or exact provider numerator/divisor observations.
NaN/infinity refuse, rather than being silently dropped or replaced.
INTEGER/BIGINT are canonical bounded decimal integer strings. JSON columns retain
DuckDB-returned text, not parsed/reformatted objects or original HTTP wire bytes.
DATE is ISO date. Stored TIMESTAMPTZ is normalized to the same UTC instant.
The original offset spelling/session timezone is not retained by that SQL type.
Other temporal types are unsupported in this profile: no naive-time UTC guessing.

Rows are canonically sorted by complete encoded content. Source key uniqueness:
option_stream=(run_id,ts,instrument_token); spot_candles=(instrument_token,interval,ts).
These keys are legacy storage identity, NOT canonical financial instrument identity.
No first/last/latest-good selection. Original source physical row order is not a
claimed chronology. Source label is caller-reviewed metadata, not authentication.

The typed projection explicitly labels iv/delta/gamma/vega/theta as legacy-derived.
It retains other fields and original stored payload_json without interpreting it
as independently authenticated evidence. Market numeric/financial correctness is
not inferred: negative or inconsistent finite stored quotes are preserved as data,
not approved as usable market inputs. No exact-price candidate is manufactured.

The projection is in-memory typed representation of retained legacy records; this
delivery does NOT persist a new Silver dataset or build Gold/publication features.
Those require separate reviewed transformation contracts. Existing Kite readers
must not consume legacy snapshot payloads as if they were provider binary frames.

## Native integration and clocks

Fresh capture occurs twice, with complete snapshot equality, and must match the
reviewed pin. Each capture uses one SQL transaction. The two checks are sequential,
not an atomic cross-resource barrier; source may change after final verification.
No claim of source-file byte hashing, global history completeness or authenticity.

The actual native Bronze producer stores ONE legacy_snapshot event containing the
bounded whole-table artifact. Bronze source is legacy_market_table_snapshot and
payload format is legacy-market-snapshot@1. The payload is a newly serialized legacy
snapshot, not original received market bytes; this does NOT relabel option_stream
as raw provider Bronze. imported_at is explicitly the receipt time of the snapshot
import. Stored market ts remains inside the payload with unresolved original
semantics. exchange_ts/provider_event_id/instrument_ref are not fabricated.

Scope binds version/table/source-label/reviewed snapshot pin. Any existing scoped
audit job blocks reuse before capture, whether successful, failed or unlinked.
No retry/adoption/cleanup. A changed snapshot is a different reviewed scope, not a
repair of old obligations. Domain commit and final audit are separate: final audit
failure can leave retained Bronze bytes with RUNNING audit. They are not accepted
by the reader. A failed domain write keeps its failed audit obligation.

The native reader requires a read-only source and exact event/envelope/snapshot
pins. It replays retained bytes, reconstructs complete native envelope equality,
rejects multiple event variants, checks the original single scoped job and exact
PLANNED/RUNNING/SUCCEEDED sequence, verifies batch fingerprint/counts and artifact
bytes. It does NOT recheck the legacy source or establish a full native lifecycle
replay/code attestation. Privileged SQL/file rollback/deletion is not prevented.

## Bounds

1..1000 rows per WHOLE table, <=64 KiB per text cell, <=1 MiB final snapshot.
Read transfers are bounded, but row and schema SQL can scan larger tables and
these are not total memory/runtime ceilings. No automatic paging or sampling;
large production tables will require a separately reviewed bounded partition
contract before real migration, not an increased limit or partial success claim.

## Validation attribution

Assistant sandbox: Python 3.12.8, DuckDB 1.2.2. 23 actual disposable DuckDB
capture/codec tests PASSED. They cover schema/view refusal, exact binary floats,
null/zero distinction, JSON text, timezone equivalence, duplicate keys, real row
and byte limits, malformed/rehashed payloads, source changes and operational errors.

11 native integration cases are supplied for repository QA, NOT run here. They use
actual Bronze/audit initialization and persistence, no substituted successful native
results. Final-audit failure injects an actual transition failure only. Other cases
exercise corruption, original-obligation refusal, retained-vs-current distinction,
domain rollback and real same-live-file cursor alias refusal with parent usability.

No assistant execution on the user's Windows CPython 3.14.2. Full pytest suites,
Ruff and mypy NOT RUN; local Git diff/branch/HEAD not inspected. Syntax, 100-column
line bounds, trailing whitespace, ZIP member equality/CRC verified in sandbox.
Sandbox success is not native acquisition-to-decision or platform acceptance.

After reviewing absent-only additions, run from repository root:

    uv run pytest tests/data_platform/test_legacy_market_snapshot.py tests/data_platform/test_legacy_market_snapshot_native.py -q
    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Check untracked additions for whitespace separately. No scripts/qa is recreated.
Preserve logs/live_status.json. No stage/commit/push/cleanup is performed.
