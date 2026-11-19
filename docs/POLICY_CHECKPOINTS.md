# Audited local policy checkpoints @1

## Reconciliation and ownership

Latest USER-REPORTED committed QA-passed baseline: 130317f on
feat/medallion-feature-store and origin. No local assistant access, independent
HEAD/branch verification, staging, commit or push. Updated sources inspected:
policy_window.py, signed_policy_window.py, native_policy_window.py,
statement_scope_policy.py, actual signed-window test fixture, and full AuditLedger.
Current public signatures/versions match new calls. No existing files replaced.
Stop/compare if any additive target exists locally. Python >=3.12 unchanged.

## New durable capability

The prior package validates only caller-supplied windows. The new writer retains
immutable local checkpoints in a dedicated owned file-backed DuckDB database and
requires exact expected-head comparison inside the domain transaction. A new window
must start at the retained head's exact tip position and advance its sequence.
Retained denied_keys may not disappear. Exact retries append audited attempts but
preserve the record's predecessor, original clock and first job. No UPDATE/DELETE.

This is local retained-store rollback resistance, NOT globally latest policy,
independently authenticated governance, secure storage against privileged SQL,
rollback protection against whole-file restore/deletion or a new database.
Different governance keys produce DIFFERENT local series; this is not authorized
key rotation. Bootstrap genesis is an explicit caller-reviewed anchor, not proof
of earlier history or a trusted root. No real checkpoints were registered.

## Namespace / contracts

Dedicated policy_checkpoint reference-control namespace, not Bronze/Silver/Gold
market observations and not a DatasetContract impersonation:
- schema_versions: native schema 1
- definitions: immutable exact store/command/bounds semantics, verified on every read
- records: content-addressed checkpoint JSON, series, first_job_id, local recorded_at
- attempts: immutable job/series/checkpoint links
Existing medallion_audit namespace is actual foundation AuditLedger.

Raw policy/source artifacts are NOT copied into this reference-control database.
Only exact hashes, endpoint positions, denied-key hashes, window fingerprint and
recording metadata are retained. Underlying original artifacts remain upstream;
there is no new policy acquisition provenance claim. No timestamps are invented
apart from explicitly local recording/audit clocks. Read clocks normalize aware
instants via astimezone(UTC), never replace(tzinfo=UTC).

## APIs

    initialize_policy_checkpoints(conn)
    read_policy_checkpoint(conn, policy_id=..., governance_key_sha256=...)
    record_policy_checkpoint(
        conn, snapshots=..., governance_public_key=...,
        expected_governance_key_sha256=..., query=ScopeQuery(...),
        anchor=PolicyPosition(...), tip=PolicyPosition(...),
        expected_previous_id=<exact checkpoint ID or None for genesis>,
        actor_id=..., code_revision=..., initialize=False,
    )

Owned single-writer connection to a dedicated existing file, no external/outer
transaction or concurrent writer. Functions do not open paths or fetch credentials.
All new SQL object references fully quote catalog.schema.object. Foreign business
tables and in-memory targets rejected. Explicit initialization only, never on read;
incompatible definition/partial nonempty schema is not silently adopted/repaired.
Initialization/foundation audit commits remain separate from recording domain.

Writer calls ACTUAL inspect_signed_policy_window, never accepts a verified DTO.
It intentionally checks the whole signed WINDOW constraint result, not tip query
permission: a signed denying tip MUST be recordable. No old-good/grant-success filter.
Tip bytes are parsed for denied-key projection only after actual full verification.
No signatures/schema replicas are used. Window raw input bounds remain unchanged.

scope series = hash([record version, exact policy_id, governance key hash]).
Checkpoint ID hashes all domain fields including predecessor/window fingerprint.
Exact retry means the same original request/query/window/endpoints/predecessor;
changing evidence at an unchanged tip is not an exact retry. Retry of an archived
record never moves current head backwards. Returned ID identifies the recorded
request; call reader for retained current head, not the returned retry ID.

## Audit, transactions and fail-closed obligations

Actual command record.policy_checkpoint@1, audit scope=series ID,
config_hash=exact candidate checkpoint ID. Foundation PLANNED -> RUNNING precedes
domain work. Full bounded scoped histories are resolved before planning new attempts
and re-read under the domain transaction. Only this exact in-flight job is allowed
to have PLANNED/RUNNING during that internal check.

Checkpoint and attempt domain inserts are atomic. Domain failure rolls both back;
FAILED audit remains. SUCCEEDED audit completion is separate AFTER domain commit.
If it fails, real rows can remain with RUNNING origin; reader and retries reject.
Later success/row existence cannot repair failed/incomplete/unlinked origin.
All prior scoped jobs need exact complete 3-state lifecycle, command, config,
actor/revision metadata, aware clocks and domain links. No latest-success shortcut.

A stale CAS that reaches execution leaves a failed audit obligation. This profile
conservatively blocks the whole series afterward, even if domain rows rolled back.
No automated repair/recovery/ignore or adoption API is supplied. Review/recovery is
a future explicitly audited contract, not delete-audit-rows. Avoid speculative writes.
Invalid signed windows rejected before planning do not create a job or claim recording.

Reader snapshots all records/attempts/jobs for the requested exact series: <=256
records, <=1000 attempts/jobs, <=6 permitted successful audit events (actual exact
3-state profile; LIMIT 7 detects extras). Record JSON <=16KiB projection before
materialization. Forks, gaps/unlinked chains, origin/config mismatch, malformed
records, denial loss, unknown schema/definition or incomplete audit FAIL closed.
No previous-good head returned on failure. Other series do not become trusted or
poison this series merely by existing; their origins are checked when read themselves.

## Evidence boundary

Positive recording means local checkpoint metadata committed under this contract.
Reader returns full local checkpoint-history fingerprint and retained head only
when scoped audit obligations resolve. No current source/Bronze revalidation, fresh
signature replay from retained bytes, issuer identity, policy authority/currentness,
economic validity, publication availability, authorized revocation or decision
eligibility is granted. The prior native admission path is NOT automatically cut over
to these checkpoints; integration/revalidation against pinned checkpoint evidence
remains a next acceptance gate. Checkpoints are not complete replay of policy sources.

## Tests and delivered checks

24 sandbox tests passed: 16 pure record/extension tests + 8 SYNTHETIC SQL reader
fixtures on REAL DuckDB. SQL fixtures deliberately are NOT AuditLedger integration
or full native E2E. They cover quoted catalog=schema, missing origins, incomplete
jobs, foreign tables, complete synthetic reads/timezone, fork rejection and link
failures. No native dependency replica/fabricated AuditLedger was used.

Six native writer/audit/signed-policy tests supplied, NOT run by assistant: actual
genesis/retry/advance/read-only/timezone, signed denying tip, stale CAS obligations,
post-domain final-audit failure, domain rollback and corrupt-definition rejection.
They import actual existing native AuditLedger and signed-window fixture; no mocked
success. Failure hooks only inject failures into actual native execution boundaries.

All Python payload syntax/line lengths/trailing whitespace verified. ZIP CRC/exact
eight-member set, all seven payload hashes and archive SHA256 verified. No actual
repository tests, full native tests, Ruff, mypy or Windows PowerShell executed here.
No full QA claim. No skips/broad ignores/loosened assertions or thresholds.

Review/copy ABSENT additions, then:

    .\scripts\qa\qa_policy_checkpoints.ps1

Runner checks branch/130317f ancestry, actual HEAD/status/runtime/dependency version,
then focused tests and ALL mandatory QA (fail-fast, no staging/commit):

    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Untracked files are not covered by git diff --check; new payload whitespace checked
separately. Preserve unrelated runtime logs. Suggested commit AFTER local passing QA:
feat(data-platform): persist audited compare-and-append policy checkpoints

No live acquisition/loading/migration/backfill/real policy or key registrations,
publication/trading/decision cutover. Synthetic disposable test data only.
Passing package QA is NOT whole-platform acceptance. Data-loading hold unchanged.
