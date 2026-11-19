# Audited adjacent-retained candle returns

## Scope

This package adds native versioned candle-series changes/simple returns over complete
actual migrated-price Gold recordings. It follows the accepted research publication
and admission-capture work; it is not a replacement for that work or a new paper loop.

Store: legacy-candle-return-gold@1.
Feature: legacy-stored-candle-returns@1.
Command: build.legacy_candle_returns@1.
DatasetContract: gold.legacy_candle_returns / 1 / VERSIONED_BUILDS.

Real-data acquisition/migration, production publication, identity/key/authority
registration, trading and cutover remain HELD. Only disposable synthetic fixtures
are exercised. Research computation never asserts independently verified truth.

## Inspected source semantics

The actual spot_candles schema supplies instrument_token, symbol, interval, ts and
stored DOUBLE close. Legacy key is token/interval/ts. Stored DOUBLE cells use exact
finite binary64 hex; retained TIMESTAMPTZ instants are canonical UTC. Partition
ordering is encoded-key order, not a general numeric/economic series sort.

The existing Gold producer retains every complete Silver input and exposes actual
revalidate_legacy_price_gold and _recording. This producer calls those actual APIs,
then reconstructs the complete original source build from full input content using
the accepted codecs. No caller-successful source result is an import API. This pure
content reconstruction is not an independent source-audit attestation; actual native
source readers remain necessary on production/revalidation paths.

The source reader/internal codec APIs are inspected dependencies. Accepted modules
and QA repairs are NOT replaced in this ZIP. This family does not reread current
legacy SQL or silently use the dormant legacy historical importer.

## Definition and computation

The kernel groups retained rows by stored token and interval, sorts each group by
stored UTC timestamp, and emits one output in original source-ordinal order. Each
output links current full source-record hash and predecessor full source-record hash,
predecessor ordinal, partition/event/capture lineage, and elapsed stored microseconds.

For adjacent retained closes c and p:

    close_change = c - p
    simple_return = (c - p) / p

All arithmetic uses Fraction over retained finite binary64, yielding reduced exact
numerator/denominator strings. It does not recover provider decimal spelling, tick
precision, corporate-action adjustments or economic identity. Rational zero is 0/1;
signed zero remains in retained input bytes. Extreme finite binary64 operands do
not overflow the rational arithmetic merely because their ratio exceeds float range.

First observation has no predecessor and no return. Missing close is not imputed,
skipped, forward-filled or bridged: the next row still references that missing row.
Zero predecessor makes simple_return unavailable, while close_change can be computed.
Negative/current-zero prices are flagged, not clipped or dropped; a nonzero negative
predecessor can produce an explicitly research-only ratio. No price is market-approved.

Unknown/empty symbol or interval prevents simple_return; a symbol change within the
token/interval group prevents that adjacent return and records SYMBOL_CHANGED_NO_BINDING.
Absolute close_change can still be computed and is not asserted economically valid.
There is no canonical symbol/token mapping or cross-symbol binding. Duplicate stored
instants within a group reject the full computation; no winner is selected.

An interval string is a retained grouping label, not an interpreted duration. The
elapsed field reports actual stored time difference. Gaps are not filled or converted
into regular-period returns, and overnight observations are not silently reset.
These are adjacent observations in the retained set, NOT proven consecutive exchange
bars. No coverage, session calendar, exchange availability or trading-hours claim is
made. coverage_verified=False remains explicit on every output.

No logarithmic return, realized volatility, RV window, annualization, rate/expiry
assumption, IV/Greeks or native solver integration is claimed. Stored legacy-derived
analytics remain only in the retained full inputs, never relabeled as recomputation.

## APIs and persistence

legacy_candle_returns.py:

- adjacent_candle_features(tuple_of_stored_fields): pure bounded kernel only.
- derive_return_records(complete_silver_records, source_build_id=...,
  source_recording_fingerprint=...): full content recomputation using accepted codecs.

legacy_candle_returns_store.py:

- CandleReturnPins(build_id, recording_fingerprint)
- initialize_candle_return_gold(empty_file_backed_target)
- persist_candle_return_gold(bronze, silver, source_gold, target, pins=...,
  actor_id=..., code_revision=...)
- read_candle_return_gold(readonly_target, build_id=...,
  expected_recording_fingerprint=...)
- revalidate_candle_return_gold(bronze, silver, source_gold, readonly_target,
  build_id=..., expected_recording_fingerprint=...)

The source profile must be a complete spot_candles Gold build; option_stream is
rejected, not filtered or promoted as a candle subset. No caller-selected row range.
All source rows and exactly one output per source ordinal are retained. Source
Gold geometry is recomputed for source-build reconciliation, not copied as returns.

One dedicated empty target and separate owned inputs are required. Close writers
before read-only reopen. Same-live-file aliases use accepted separation semantics;
public readers enforce actual readonly=True. Domain SQL and tests use fully quoted
actual catalog.schema.table identifiers, including gold.duckdb/gold schema collisions.

Native AuditLedger and actual DatasetContract are reused. First-write scope binds
profile plus source Gold build ID, excluding recording pin/runtime/actor labels.
Original jobs, builds, attempts or orphan source rows block another write before
source observation. Changing a failed review pin cannot heal the obligation.

Two complete actual source observations must agree. Build/inputs/outputs/attempt
commit atomically; final audit SUCCEEDED remains separate. Domain rollback retains
a failed scoped audit. A post-domain final-audit failure leaves unreadable content
that cannot be adopted. There is no retry/recovery/history or repair operation.

Retained reader rebuilds complete source content and every feature/materialized SQL
scalar, build ID, definition/contract, exact runtime and original scoped job/link/audit
obligations. Extra same-source rows under other build IDs are included in coverage
checks, not hidden behind a good subset. Separately reviewed recording fingerprint
binds execution/recording clocks as well as content. UTC normalization preserves
instants in non-UTC SQL session timezones.

Current-native revalidation additionally invokes actual source Gold/Silver/Bronze
readers and compares complete inputs/features. Retained replay is not that live check.
Neither claims current legacy SQL equality. Repeated observations are not an atomic
cross-database/time snapshot. Runtime labels are not authenticated build attestation;
exact current runtime equality is inherited deliberately from source Gold @1.

## Independent bounds

- 1..16000 complete source rows; original source row/artifact/partition bounds unchanged.
- Full input rows <=512 KiB each; aggregate <=32 MiB.
- Return output rows <=64 KiB each; aggregate <=32 MiB.
- Context <=32768 bytes; source pins <=512 bytes.
- Aggregate SQL count/byte preflight for inputs AND outputs before BLOB transfer.
- Independent per-row/context CASE guards, bounded metadata/inventory/link/job/event reads.

The pure kernel bounds row count, close spelling, token range, aware UTC time and
individual text cells. Its caller already owns those field objects. Native full-input
codec validation applies aggregate source bounds before projection. No streaming or
peak-memory ceiling is claimed: source replay, JSON and sorting create multiple copies.
No paging, automatic salvage, limit inflation or limit-prefix success is allowed.

## Publication and decision boundary

Every output retains null canonical identity/published_at, false availability,
economic validity, publication assertion and decision eligibility. Existing geometry
bundle/publication @1 does NOT accept this new feature family. There is no silent
codec widening or production publication. This package adds native source-linked
analytics, not eligible publication/admission or a strategy-loop cutover.

## Tests and verification attribution

The kernel test suite was independently executed by the assistant: 23 passed on
Python 3.12.8, without source-success substitutes for the numerical kernel. Cases
cover chronological remapping, grouping, symbol drift, missing/no bridging, signed
zero, negative prices, exact binary64 rational values/extremes, gaps, duplicate
instants, invalid hex/nonfinite cells, naive/noncanonical clocks and row bounds.

Native tests use actual accepted legacy -> partition Bronze -> persisted Silver ->
Gold fixtures, then the new producer/retained/current readers. They include full
1001-row/two-partition coverage and an actual multi-row candle series, plus content/
scalar corruption, incomplete original obligations, wrong pins, scoped failures,
real SQL rollback, final-audit failure, transfer limits and source-clock distinctions.
These repository-dependent tests have NOT been assistant-executed.

Syntax, line-length/trailing-whitespace and exact ZIP members/CRC/payload equality
are checked before delivery. Isolated SQL checks, if performed, have separate explicit
boundary attribution in the delivery response; they are not native E2E.
No assistant Windows/uv-selected interpreter, repository execution, full pytest,
Ruff, mypy, Git worktree/commit/push verification occurred. User-confirmed QA through
bee02fd remains accepted/closed and does not cover these new additions.

## Application and QA

Review/copy absent additions only; stop/compare if any destination exists. Accepted
source modules/QA repairs, logs/live_status.json and scripts/qa are untouched. No
PowerShell QA runner, per-payload SHA256 manifest or standalone verifier is supplied.
pytest-xdist was discussed but is not installed/configured or made default here;
this package does not certify full-suite parallel safety or speedup.

    uv run python -c "import sys; print(sys.executable); print(sys.version)"
    uv run pytest tests/data_platform/test_legacy_candle_returns.py -q
    uv run pytest tests/data_platform/test_legacy_candle_returns_native.py -q
    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Also check untracked additions for whitespace. These are new-work checks, not a
request to reopen completed QA. Package acceptance is not whole-platform acceptance
or permission to release any operational/data/trading holds.

### Isolated actual new SQL/materializer checks

The assistant executed the actual new DDL, persistence/materializer and retained
reader against disposable DuckDB 1.2.2 files. A three-row exact return roundtrip
passed. Seventeen further isolated checks passed: content/scalar corruption,
original row/link/audit/contract obligations, input/output aggregate and per-cell
limits, timezone original-pin invariance, actual SQL domain rollback and post-domain
final-audit refusal/no adoption. Source Gold/codecs, native audit/contract and lifecycle
boundaries in this SQL harness were explicit adapters. These results verify new SQL
and materialization paths under those boundaries, not native source attestation or
repository producer/reader E2E. The actual repository tests remain supplied/unexecuted.
