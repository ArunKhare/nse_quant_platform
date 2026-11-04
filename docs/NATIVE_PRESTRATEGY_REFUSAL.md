# Native audited pre-strategy refusal decisions

## Baseline and dependency reconciliation

Latest USER-CONFIRMED committed/pushed QA baseline: 78272d0 on feat/medallion-feature-store.
The signed temporal package is present in uploaded sources but no later commit hash or QA
acceptance was reported. This delivery neither assumes that package accepted nor modifies it.
No outstanding new failure was reported. No direct repository/terminal connector is available.

Inspected actual current native_publication_temporal.py, signed_temporal_evidence.py, legacy
strategy/iron_condor.py, strategy/gates.py, core/settings.py, decision_loop.py and native
admission_capture.py. Existing admission capture already retains policy receipts; it is NOT
rebuilt or renamed here. Existing legacy paper-loop persistence/order execution is untouched.

This package adds a DISTINCT decision-stage contract and dedicated audited native decision
recording profile. It records an actual ordered pre-strategy refusal, not a successful strategy
or risk outcome. It imports no legacy adapter, strategy engine, risk engine or broker at runtime.

## Implemented scope

native_strategy_requirements.py documents/version-pins the DIRECT iron-condor proposal input
requirements observed in actual strategy/gates, including candidate wing selection, nullable
IV rank/history cold-start policy, IV-RV spread, expected move, market session, and CE+PE checks
at every selected strike. Liquidity warnings and fallback semantics are described, not changed.
It does NOT claim the full loop/portfolio-risk/plugin input set is complete or available natively.
No arbitrary historical future-plugin list is treated as mandatory implementation scope.

native_refusal_decision.py implements strict request validation, deterministic gate ordering,
retained full inputs/results, source/code/runtime pins and complete original refusal replay.
native_refusal_service.py obtains two ACTUAL native point-in-time admission observations when
allowed by the earlier safety checks; both complete encoded observations must agree. It never
accepts a caller-created successful source DTO or a positive-admission override.
native_refusal_store.py evaluates that actual service under the existing AuditLedger, retains
the complete decision entry and job links, and independently replays it before persistence.

## Gate and negative ordering contract

1. Kill switch ACTIVE or UNKNOWN refuses before source observation.
2. Live request, disabled dry-run or non-paper boundary refuses next, in that exact order.
3. Missing source is explicitly ADMISSION_NOT_OBSERVED. Operational DB/SQL errors propagate.
4. Actual admission observations must match the exact publication, both explicit time axes,
   current supported policy/reader/code context, and the reviewed publication fingerprint.
   Different complete observations refuse even if both policy status strings are REJECTED.
5. Existing research point-in-time rejection is retained verbatim under the decision reason.
6. Native-input binding, strategy, portfolio risk and execution remain NOT_RUN.

There is no positive lane in this @1 contract. A caller saying the switch is inactive cannot
cause a proposal, risk approval, order or trading. Safety fields are explicit REQUEST observations,
NOT authenticated live kill-switch measurements. Unknown remains unknown; live is always disabled.
This module is not wired into a running loop and does not replace the operational KillSwitch.

The input inventory uses NOT_OBSERVED for early/missing-source refusal and NOT_ADMITTED for an
observed denied source. It does not invent MISSING, STALE, READY, native IV or canonical inputs
that were never read. No options/analytics/portfolio data are loaded after admission refusal.
The inventory's scope is explicitly not a full portfolio-risk or paper-loop completeness claim.

## Complete replay — narrowly defined

The immutable entry retains the full request, normalized separate knowledge/economic times,
explicit reviewed 40-character code revision, actual new-module source hashes, Python context,
actual admission/reader source hashes and DuckDB version when admission was observed, both full
native admission receipt bytes, every ordered stage result, inventory states and refusal reasons.

Replay verifies the entry hash, strict original canonical bytes, exact current supported code/
runtime/dependency context, full original admission-policy replay and complete decision equality.
Rehashed status/strategy/execution/eligibility changes cannot pass. No DB/current-source calls are
made during replay. Changed recorded/current code or runtime does NOT refresh fingerprints; it
requires review and an appropriate separately retained compatible replay environment.

This fully replays the actual original PRE-STRATEGY refusal, including why later stages did not
run. It does NOT claim that a strategy, portfolio risk or execution ran, or that complete original
strategy/decision-loop replay is solved. Content/code pins are not authenticated build attestation,
proof of a clean worktree, source authenticity, legitimate authority or every environment dependency.
The reviewed revision is a supplied identifier; the QA runner verifies actual local HEAD separately.
Full current-source validity/authority cannot be recovered by replaying an old-good refusal.

## Audited recording semantics

Use a dedicated owned file-backed native decision DB, separate from source files and aliases.
Schema has immutable complete entry records and attempt links; no generic receipt-import API.
An explicit attempt_id has one immutable first-write binding. Reusing it is refused BEFORE source
reads/planning; a forbidden retry does not poison a good original recording. Scoped earlier failed/
incomplete/unlinked work blocks later adoption. Different attempts do not repair old obligations.

Initialization, domain+attempt commit and final audit success are separate. A final-audit failure
can leave complete domain bytes and a RUNNING job. The profile has no retry/adoption/supersession/
cleanup API. A domain-link failure rolls back domain records but retains its failed audit obligation.

Readers require exact decision ID AND separately reviewed full recording fingerprint. They verify
all scoped job/link coverage, original job/config/revision identity, exact successful lifecycle,
complete decision replay and full recording metadata/audit fingerprint. No auto-latest selection,
old-good cache, repair or fingerprint refresh. Use owned read-only inputs, no outer transaction.
Matching rows does not prevent privileged SQL/file rollback/deletion or authenticate original data.

## Bounds and safety

- Entry/retained input <=8 MiB; embedded admission receipt bytes have stricter per/aggregate
  encoding bounds. Large otherwise valid admission receipts can be rejected, never salvaged.
- <=256 scoped audit jobs/links, bounded event/metadata transfers and exact schema inventory.
- Known code-source files read with a <=1 MiB per-file bound; these are computation-context pins.
- Actor <=128 characters; explicit attempt ID <=128, full lower-hex 40-character revision.
Payload/coverage limits are not total process-memory ceilings. Existing dependency, solver,
numerical, source/temporal, authority and publication bounds/contracts are unchanged.

## Tests / acceptance ledger

Pure tests: gate precedence, early no-source/no-execution imports, NOT_RUN stages and honest
inventory, full refused-entry replay, rehashed tampering, context drift, strict bytes, real byte
capacity and request types. Native tests seed the accepted real producer path via NativeFailureLab,
then exercise actual admission -> audited decision -> read-only complete replay, first-write
refusal, early unknown-switch capture, final audit failure, domain rollback, unlinked scoped work,
SQL failures, reviewed recording pins and original replay after current publication changes.
No native successful result is mocked. Only an actual final-audit write is fault-injected.

| Gate | Added capability | Unresolved |
|---|---|---|
| Governance/identity/time | Existing research refusals preserved | Independent real evidence and positive eligible contract |
| Required native inputs | Source-reconciled direct proposal requirement inventory | Actual canonical PIT input producers/bindings, full risk/loop coverage |
| Native decisions | Actual ordered refusal and audited complete persistence | Proposal/strategy/risk evaluation and positive admission |
| Replay | Complete original pre-strategy refusal + admission-policy result replay | Complete strategy/loop/execution replay and source authenticity |
| Operations | Disposable audit/domain failure tests supplied | Live-switch attestation, concurrent races, real operational acceptance |

Assistant executed 14 NEW refusal-kernel/early-service tests in sandbox: PASSED. They do not
exercise native admission or native audit/storage. No dependency replica or successful native
substitute was created. Native integration tests supplied, NOT independently executed here.
Repository full pytest/Ruff/mypy/Git/Windows uv NOT RUN. AST, line-length, whitespace and ZIP
CRC/member/checksum verification executed. Prior user QA accepted, not independently reproduced.
No production eligibility, whole-platform acceptance, completion percentage or loading release.

Apply additive payload only after archive verification. qa_native_refusal.ps1 checks reviewed
full local HEAD/branch, prints actual uv interpreter, runs focused + mandatory QA and whitespace
on tracked/untracked payloads. It never stages, commits, pushes or deletes logs. Tests use only
disposable synthetic data. No acquisition, migration, authority registration, production
publication, trading or loop cutover occurs.
