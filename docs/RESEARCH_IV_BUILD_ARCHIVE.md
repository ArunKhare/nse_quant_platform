# Audited versioned research-IV build archive @1

## Reconciliation and delivery scope

Latest USER-REPORTED QA-passed committed baseline 7fa0168 on
feat/medallion-feature-store and origin. Assistant has no direct repository/HEAD/
branch access, no staging, commit, push or repository QA execution.
Inspected actual uploaded Gold quote writer/reader, DatasetContract, native Gold
transaction tests and existing SQL-reader fixture. Three source lookups did NOT
return new research_option_model/native_research_option sources or their new fixture.
Dependencies therefore use the last explicitly delivered, now reported committed
public interface, with runtime version gates. No claim that newest analytics source
was independently reconciled; local integration is mandatory. Existing files and
committed fixes (including fetchone None assertions) are not copied/replaced.
Python >=3.12 and actual SciPy>=1.14 requirement unchanged.

This package adds audited immutable Gold ANALYTICS STORAGE and an invalidation-first
ARCHIVED reader. It does NOT add a current-source consumer for stored builds,
publication, eligible features or full exact decision replay. Native computation
is freshly executed on each write; archive reads do not pretend to recompute it.

## Owned objects / true native contracts

Separate dedicated existing file-backed single-writer target, distinct from ALL
source handles/files (including attachments/hardlink/same-file aliases):

    gold.research_iv_schema_versions
    gold.research_iv_definitions
    gold.research_iv_builds
    gold.research_iv_attempts
    medallion_audit.<actual foundation objects>

Actual DatasetContract gold.research_iv_builds@1, Layer.GOLD,
WritePolicy.VERSIONED_BUILDS, real required build_id/event_ts/published_at/feature_version
columns. No fake contract type, widened enum or legacy namespace. Target refuses
other business tables. Source native Gold remains a separate input; no writes to it.

Definition binds store/native/model versions and actual exported numerical profile
parameters, not an authority root. Same-version changed contract/definition rejects;
no adoption/overwrite. New definition/content differences need an explicit version
contract, not loosening checks. Initialization is explicit, never on archive reads.
Partial nonempty versionless domain schema not silently adopted.

DatasetContract registration, new definition, new build AND attempt all commit in
ONE domain transaction. Actual AuditLedger.register_contract is invoked INSIDE that
transaction (its inspected API has no nested begin). Foundation/schema initialization
and audit lifecycle commits remain separate. First definition job is verified in its
OWN input scope, including full origin scope history/audits, not the requested scope.

## Input/result identity and history

Input group hashes ordered option/spot build IDs, exact scenario-terms pin,
record version and definition fingerprint. It intentionally excludes current source
status: a newer review_required observation must remain in the SAME input history.
Model/runtime/SciPy context remains inside original candidate/result identities.

Build ID hashes the complete bounded original candidate JSON and input group.
Writer accepts NO caller result/DTO. It calls actual
build_native_research_iv_candidate on every attempt and persists both
research_iv_candidate and review_required results. An actual raised computation/
SQL failure produces a FAILED audit, not an invented review result.

Every new distinct record links ALL earlier IDs in scoped ordinal order, regardless
of status. These are prior EVIDENCE links, not authoritative permission to supersede
identity. Exact retries preserve ordinal, prior links, first_job_id, recorded_at and
original result; only a new audited attempt is appended. Retrying old-good bytes
never revives an older head after a newer distinct review result.

Archival current-head means last distinct local evidence position, NOT source truth,
market currentness or globally latest analytics. No latest-success filter.
<=256 builds, <=1000 scoped jobs/attempts. Exact 3-state success only;
PLANNED/RUNNING allowed only for the exact writer job during its domain recheck.
JSON result <=1MiB, terms<=4KiB, all-prior links<=32KiB; bounded projections and
LIMIT+1 precede materialization of those payloads. Strict canonical JSON rejects
duplicate/nonfinite/unknown representation, no prefix salvage.

## Audit failures / no old-good fallback

Command build.research_iv_scenario@1, scope exact input group,
config exact definition hash. Full scoped records/attempts/jobs and full state
sequences checked before planning another job and under the domain transaction.
All jobs require linked domain attempts and exact command/config/metadata; original
build/definition origins require THEIR successful linked attempts. Failed/incomplete
or unlinked prior jobs block. Later success cannot discharge an earlier obligation.

Final SUCCEEDED audit completion happens AFTER domain commit. A failed final audit
may leave real domain rows with RUNNING origin. Reader/retries reject, never adopt,
repair or select an older good row. Domain insert failures roll back contract/
definition/build/attempt changes while FAILED audit remains. No automatic recovery
contract is supplied; conservative scoped blocking remains an operational gate.

## Public APIs

    persist_research_iv_build(
        bronze, frame_silver, reference_silver, assessments, source_gold, target,
        option_build_id=..., spot_build_id=..., terms=ScenarioTerms(...),
        expected_scenario_terms_sha256=..., actor_id=..., code_revision=...,
        initialize=False,
    )

    read_research_iv_archive(target, build_id_pin=<exact stored pin>)

Owned input connections/native source contracts, output single owner, no enclosing
transactions or concurrent writers. No path/DB opens, acquisition or credential lookup.
All new SQL table references fully quote catalog.schema.object. Parent/child cursor
alias checks use actual same-file metadata and keep parent usable; no second live
independent ATTACH. Windows-safe physical filenames only in supplied tests.

Archive returns exact stored result/terms JSON, recorded business status, retained
head ID, full fingerprint and archived_pin_is_head. Superseded pins return review
status with archive evidence, never become current. Fingerprint includes requested
scope AND definition/contract metadata and full definition-origin scope fingerprint.
No current-source recomputation, pricing solver execution or present source validity
is asserted by archive verification. No source acquisition authenticity granted.

Generic SQL event_ts stays None: two source quote times do not imply one common
analytics event/economic time. Each original source time, including None, stays
inside the untouched candidate JSON. Local recorded_at is local admin metadata only.
published_at stays None. No expiry/receipt/availability/economic-time inference.
All publication/historical-validity/identity/eligibility flags remain false/None.
Do not log full result_json indiscriminately: it contains source market evidence.

## Tests and verification attribution

23 sandbox tests passed: 15 pure record/identity/strict-encoding tests + 8 SYNTHETIC
SQL scope-reader tests using REAL DuckDB. No native source/audit dependency replica
was built. These are NOT actual AuditLedger integration or full native E2E.

Seven additional integration tests supplied, NOT run here. Actual audit/store/model/
Gold SQL reader use the prior analytics fixture, whose LOWER SOURCE KERNEL IS
SUBSTITUTED. This is explicitly mocked-source boundary integration, NOT full native
Bronze/Silver/Gold end-to-end verification. Cover exact retries/origin preservation,
review successor + no old-good revival, final audit failure, atomic domain rollback,
definition origin own scope, read-only/timezone and cursor/same-file rejection.
No candidate or numerical success result fabricated by the new tests.

No actual repository checks, supported SciPy>=1.14 integration, Ruff, mypy or Windows
PowerShell executed here. Python syntax, line lengths/trailing whitespace checked.
ZIP nonempty/CRC/exact eight-member set, seven payload hashes and archive checksum
verified. No skips, broad ignores or weakened assertions/thresholds.

Review/copy ABSENT additions; if target exists, stop/compare. Run:

    .\scripts\qa\qa_research_iv_archive.ps1

Runner verifies expected branch/7fa0168 ancestry, actual HEAD/parents/status,
Python>=3.12/SciPy>=1.14/native version, then focused and ALL mandatory QA, fail-fast:

    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

No staging/commit. Untracked whitespace verified separately, preserve unrelated logs.
Suggested commit ONLY after actual local passing QA:
feat(data-platform): persist audited versioned research IV builds and archive history

No live acquisition/loading/migration/backfill, actual identities/keys/policies,
publication/trading/decision-loop cutover executed. Only synthetic disposable tests.
Next separate gates: native CURRENT-source revalidation of archived IV builds,
audited analytics bundles, authoritative role/identity/time evidence and eligible
publication/native decision replay. Package acceptance is not platform completion;
user-data loading/migration hold remains unchanged.
