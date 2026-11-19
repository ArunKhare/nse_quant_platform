# Policy-explicit research windows over retained candle returns

## Scope and versioned contract

This additive family consumes complete actual legacy-candle-return-gold@1 recordings.
It adds reviewed fixed-elapsed window rules and exact sum/mean squared SIMPLE returns,
not a silent extension of the legacy paper loop or a numerical kernel disconnected
from native persistence. It does not claim conventional realized volatility.

Store: legacy-return-window-gold@1.
Feature: legacy-fixed-elapsed-simple-return-windows@1.
Command: build.legacy_return_windows@1.
DatasetContract: gold.legacy_return_windows / 1 / VERSIONED_BUILDS.

User-confirmed QA through a0ef04a is accepted/closed. Supplied local HEAD/origin match
at that short hash; no assistant Git/worktree inspection or push occurred. The user
also supplied a919045 for distributed-testing dependencies. Older pyproject retrieval
does not negate that commit. This ZIP does not replace pyproject.toml, uv.lock, test
scheduling defaults or any accepted source/QA repair.

Real acquisition/loading/migration, production publication, authority/identity/key
registration, trading and cutover remain HELD. Only disposable synthetic tests are
permitted. No native strategy/risk/execution stage is added or replayed here.

## Why the policy is explicit

The accepted adjacent-return family deliberately does not prove regular-grid bars,
trading sessions, authoritative symbol binding or independently timed availability.
Rolling over available good rows or assuming an interval label is a duration would
hide gaps and change the interpretation of a statistic.

ReturnWindowPolicy requires TWO reviewed integers:

- window_returns: 2..256 returns, requiring N+1 consecutive retained close observations.
- cadence_microseconds: 1..86400000000 exact elapsed UTC microseconds per adjacent step.

Neither value is inferred from a filename, exchange, symbol, source interval label,
annualization convention, number of trading days or market calendar. They are
research assumptions, not authority evidence or production configuration defaults.
The policy bytes enter scope, build identity, output records and audit config.

Different policies are genuinely different builds. Changing a source recording pin,
runtime or execution label cannot create a new scope for the same source/policy.
A distinct policy does not heal an original failed obligation for the old policy;
no recovery/history-head or whole-database acceptance claim is made.

## Complete-window computation

The actual accepted adjacent-return kernel is reused. Group by retained token and
interval, order stored canonical UTC instants, and emit one record per original source
ordinal, including warmup/invalid windows. A full window requires all of:

- Exactly N+1 consecutive retained observations ending at that source observation.
- Known nonempty stable symbol and interval label across that entire window.
- Every close finite, present and strictly positive.
- Every adjacent stored time difference equals the explicitly reviewed cadence.
- Exact predecessor linkage; no skipping missing/invalid observations or joining groups.

Insufficient warmup, gaps, missing/nonpositive values, unknown labels or symbol drift
produce UNAVAILABLE and explicit reason codes. These rows are not dropped. After
invalid observations/gaps leave the complete N+1-row window, a valid suffix can compute.
No imputation, padding, forward-fill, bridging, clipping or good-subset salvage exists.
Duplicate instants reject the entire source computation through the accepted kernel.

For N simple returns r_i over that complete retained window:

    sum_squared_simple_returns = sum(r_i * r_i)
    mean_squared_simple_returns = sum_squared_simple_returns / N

Fraction arithmetic gives exact reduced rational numerator/denominator strings over
retained binary64 closes. There is no floating-point square-root step. The mean is
not sample variance, demeaned variance, standard deviation, annualized volatility or
log-return realized variance. No rate, expiry clock, trading-day/calendar scaling,
market session reset, corporate-action adjustment or IV/Greeks is inferred.

policy_cadence_matched=True describes only full-window timestamp/cadence agreement;
policy_window_satisfied also requires the price/symbol/domain gates. A missing close
can leave cadence matched but the statistic unavailable.
authoritative_market_coverage_verified remains
False, even for computed windows. No exchange-calendar or expected universe coverage,
source acquisition completeness, identity, availability or economic validity is proven.
A cadence can match across midnight; it does not authenticate a valid trading session.

Each output retains ordered member source ordinals and a digest binding the ordered
original return-record hashes, current source-return hash, partition/event lineage,
policy, source return build and separately reviewed recording pin. Original full Silver
inputs are retained once in the new dedicated store; source returns and all window
membership/statistics are fully recomputed on replay.

## Native APIs and data flow

legacy_return_windows.py:

- ReturnWindowPolicy(window_returns, cadence_microseconds)
- window_statistics(complete_stored_fields, policy=...): pure research kernel.
- derive_window_records(complete_inputs, complete_return_rows, source_build_id=...,
  source_recording_fingerprint=..., policy=...): complete content-only projection.

legacy_return_window_store.py:

- ReturnWindowPins(build_id, recording_fingerprint)
- initialize_return_window_gold(empty_dedicated_file)
- persist_return_window_gold(bronze, silver, geometry_gold, return_gold, target,
  pins=..., policy=..., actor_id=..., code_revision=...)
- read_return_window_gold(readonly_target, build_id=...,
  expected_recording_fingerprint=...)
- revalidate_return_window_gold(bronze, silver, geometry_gold, return_gold,
  readonly_target, build_id=..., expected_recording_fingerprint=...)

Actual complete source revalidate_candle_return_gold and _recording are invoked,
including their original native audit obligations. The source context is read through
an explicit bounded CASE guard. Complete source returns are reconstructed using actual
accepted _recompute/_id, thereby checking original return build identity, full Gold
geometry/Silver content and exact current runtime restrictions. This deterministic
reconciliation is NOT independent source audit attestation; actual source readers
are still required on native production/current-revalidation paths.

Two complete native source observations must agree before persistence. No caller-
successful result or raw offline artifact import is available. Private source/helper
APIs are inspected dependencies; future incompatible changes require a new review.

## Audit, first write and replay

The dedicated native target uses actual AuditLedger and DatasetContract. First-write
scope binds store version, source return build and explicit policy, excluding source
recording fingerprint and execution identifiers. Prior scoped builds, rows, attempts
or audit jobs block new writes before observation. There is no adopt/heal/retry API.

Build, full inputs, all outputs and original attempt link commit in one transaction.
Domain failure rolls all those back but retains the original failed audit obligation.
Final SUCCEEDED audit is a separate transaction. Its failure may leave committed
content, but that content cannot be read as valid or adopted by another attempt.

Retained replay rechecks definition/contract, all full inputs, source-build identity,
all window bytes and materialized indices, exact scope/build/policy/pins, original
job/config/lifecycle and attempt links. Same-scope/build rows and unlinked scoped
jobs cannot hide behind a good subset. A separately reviewed recording fingerprint
binds execution/record clocks as well as content. UTC normalization preserves instants
under SQL timezone changes. Audit integrity is not a DB permission/authority boundary.

Current-native revalidation additionally invokes actual return/geometry/Silver/Bronze
readers and compares complete input/output reproduction, bracketed by pinned retained
window reads. Retained replay does not assert current upstream. Neither API checks
current legacy SQL equality. Repeated observations are not atomic cross-database time
truth, independent availability or point-in-time decision evidence.

Connections are caller-owned; no shared writer or outer transaction. Initialize an
empty file explicitly, close writers before readonly reopen, and preserve accepted
same-live-file alias rejection. New SQL and tests quote actual catalog.schema.table,
including real gold.duckdb/gold-schema collision fixtures.

## Independent resource bounds

- Source row count 1..16000; original source profile limits remain unchanged.
- Full retained inputs <=512 KiB each and <=32 MiB aggregate.
- Window outputs <=64 KiB each and <=32 MiB aggregate, independently of row count.
- Policy/pins each <=512 bytes; retained wrapper context <=70000 bytes.
- Original nested source context <=32768 bytes, encoded as <=65536 hex characters.
- Definition/contract <=32768 bytes; bounded object/metadata/job/link/event inventory.
- SQL aggregate count/byte preflight for BOTH inputs and outputs before BLOB transfer.
- Independent per-row/context CASE guards.
- Exact intermediate rational numerator/denominator <=8192 bits after each square/add
  and mean division. Resource overflow rejects the entire computation/build; it is
  not a missing observation or an UNAVAILABLE business result. No integer-string
  process limit is disabled or inflated.

The straightforward rolling kernel performs at most 16000*256 bounded rational
accumulations. Source replay and JSON materialize multiple copies; no streaming,
scan-cost or peak-process-memory ceiling is claimed. Large legitimate input may
still fail an independent output/rational bound. There is no automatic limit growth,
paging, truncation, approximate fallback or partial build.

## Publication/decision boundary

Every output retains null canonical identity/published_at and false independent
availability, economic validity, publication assertion and decision eligibility.
Existing geometry research-bundle/publication @1 is NOT widened to accept window
statistics. This family supplies versioned native research analytics, not sufficient
eligible publication/admission. There is no authority, allow-unknown or force-eligible
bypass. Existing decision/refusal consumers and legacy paper loop are unchanged.

## Tests, delivery and verification attribution

The pure suite covers exact sum/mean definitions, N+1 warmup, explicit cadence versus
interval label, gaps, missing/no bridging, strict-positive domain, symbol drift,
chronological remapping, group isolation, policy types/ranges, rational bounds and
duplicate instants.

Native tests use actual accepted synthetic legacy -> partition Bronze -> Silver ->
geometry Gold -> persisted returns -> window producer/retained/current-reader paths.
They include 1001-row/two-partition coverage, a real custom series with gap/recovery,
original jobs/links/rows, distinct policies, changed pins, corruption, actual SQL
rollback, final-audit failure, both SQL transfer budgets and timezone normalization.
Repository-native tests are supplied, NOT assistant-executed unless explicitly stated
otherwise in delivery verification. Failure injections do not substitute successful
source DTOs and call them full E2E.

Assistant pure/isolated checks, if run, are separately attributed in the delivery
response. Syntax, line lengths/trailing whitespace, ZIP exact unique members/CRC and
payload equality are checked before final delivery. These checks are not Windows/uv,
full pytest, Ruff, mypy or native integrated acceptance. No repository writes, Git
inspection, commits or pushes are claimed. No package QA establishes platform acceptance.

Copy absent additions only; stop/compare if a destination exists. No accepted module,
QA repair, runtime log, scripts/qa, PowerShell runner, payload-hash manifest or standalone
ZIP verifier is included/replaced. Preserve logs/live_status.json. Distributed pytest
dependency work is retained; this ZIP does not change scheduling or certify parallel
safety/speedup. Historical delivery-time QA statements do not reopen closed QA.

New-work checks:

    uv run python -c "import sys; print(sys.executable); print(sys.version)"
    uv run pytest tests/data_platform/test_legacy_return_windows.py -q
    uv run pytest tests/data_platform/test_legacy_return_window_native.py -q
    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Check untracked additions for whitespace too. All data/production/trading holds remain.

### Assistant-executed checks for this delivery

Python 3.12.8 / DuckDB 1.2.2 sandbox:

- Final pure policy/arithmetic suite: 26 passed. The inspected accepted adjacent-return
  kernel was transcribed into a temporary dependency harness, not executed from a
  repository checkout. No successful source-recording DTO was substituted and called
  a native numerical E2E result. Accepted dependency files are not in this ZIP.
- Actual new DDL/materializer/retained-reader roundtrip passed on a four-price series;
  warmup/unavailable rows and exact computed values were checked. A second distinct
  reviewed policy produced a separate valid build in the same dedicated target.
- 17 additional isolated SQL/filesystem checks passed: materialized content/scalar
  corruption, original row/link/audit/contract obligations, both aggregate/per-row
  transfer limits, timezone original-pin invariance, real SQL domain rollback/no
  adoption, and post-domain final-audit retained refusal/no adoption.
- SQL harness source/audit/contract/lifecycle boundaries were explicit adapters.
  These checks establish new SQL/materialization behavior under those boundaries,
  not native source attestation, repository integration, Windows acceptance or E2E.
- Final Python syntax/line lengths/whitespace and ZIP exact unique members/CRC/payload
  equality were checked. Ruff/mypy/full repository tests were NOT run.

Repository-native tests are supplied/unexecuted. User-confirmed QA through a0ef04a
remains closed; that accepted QA does not cover these additions. Native verification
must not be inferred from syntax, pure computation or isolated SQL success.
