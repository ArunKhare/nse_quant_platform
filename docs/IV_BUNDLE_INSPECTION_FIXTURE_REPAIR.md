# Test-only inspection fixture repair

## Actual failure and baseline

User reported 5 failed / 39 passed focused tests, Ruff SIM117 twice and mypy
var-annotated twice. These failures remain OPEN until local QA passes after repair.
Latest user-confirmed accepted commit is local 092d936; reported origin is c9c6c42.
No later commit/push or full QA success is claimed. Direct repository writes are
unavailable. The prior inspection candidate was not accepted by this failing run.

Root cause: inspected test_gold_quote_reader.setup creates four source connections
AND Gold in memory. Their selected PRAGMA database_list path is None. The generated
readonly_arguments helper wrongly asserted physical files for all seven inputs.
All five reported failures occur before CLI execution. They do not establish a
production source-revalidation failure. The original scenario source substitute
also asserts exact connection identities against the captured mutable sources list;
reopening files requires precise role-handle rebinding, not weakening that assertion.

## Repair delivered

New test-only helper snapshots only memory fixture databases into safe-named
DISPOSABLE files using actual DuckDB COPY FROM DATABASE, with separately quoted
catalogs/aliases. It never invents either archive: those must already be file-backed.
It closes file-backed owners before read-only reopen and retains memory owners for
existing captured fixture closures/teardown. Snapshots retain actual current SQL
rows, including all Gold evidence and timestamps; no analytical result is fabricated.

A local autouse adapter wraps the actual CLI connection context. During execution
only, it binds the original fixture's captured four source-role expectations to the
ACTUAL reopened read-only handles. It restores them in finally, including errors.
The original substituted source function and its exact identity assertion remain
unchanged. Actual Gold readers, native model/SciPy computation, archive services,
CLI read_only flags, pins, expected statuses, denial flags and file-hash assertions
are not replaced or weakened. This remains lower-source-boundary integration, not
full native acquisition E2E.

A guarded source-edit tool changes ONLY the faulty readonly_arguments helper,
adds that test-local adapter/imports, annotates result: list[str], and combines the
two with contexts without removing their assertions. The removed helper's args
list no longer exists, fixing the other mypy finding. Unrelated test bodies and
prior Ruff fixes are preserved. Unknown/already-repaired layouts fail for review.
No shared foundation fixture or production file is changed.

## Apply carefully

Copy the six additive repair payloads and repair checksum manifest into their
repository-relative paths, first checking that they do not overwrite existing files.
The tool defaults to PLAN (reads/validates files, no writes):

```powershell
uv run python scripts/qa/repair_iv_bundle_inspection_tests.py
```

Inspect actual `git status --short`, `git diff`, branch and `git rev-parse HEAD`.
Then explicitly apply using that reviewed FULL 40-character local HEAD, not short
092d936, a filename or ZIP checksum:

```powershell
uv run python scripts/qa/repair_iv_bundle_inspection_tests.py --apply --expected-head FULL_REVIEWED_40_CHARACTER_HEAD
```

The placeholder above must be replaced. Actual branch must be
feat/medallion-feature-store and actual HEAD must match. It edits two tests plus
the TWO matching entries in RESEARCH_IV_BUNDLE_INSPECTION_SHA256SUMS.txt. Other
manifest entries remain unchanged. This manifest is then a LOCALLY DERIVED repaired
working-tree manifest; it is no longer a verbatim original delivery manifest.
The old ZIP and its old archive checksum are NOT changed or newly attested.
The repair's separate checksum manifest/ZIP cover the new repair payloads.

All edits are prepared and compiled before writes. Multi-file writes are NOT an
atomic transaction. On any failure stop, retain/review the diff and reconcile; no
automatic rollback, overwrite of unrelated changes, stage, commit or push occurs.
The tool refuses a second apply rather than guessing how to rewrite repaired code.
If local auto-fixes already combined the contexts, stop and reconcile rather than
forcing the edit tool. Original/Ruff-adjusted formatting outside targets is retained.

## QA

Run scripts/qa/qa_iv_bundle_inspection_repair.ps1 with -ExpectedHead and the reviewed
full local hash. It checks repair hashes, runs the added SQL/helper regressions,
then invokes the existing inspection QA runner, which executes every mandatory QA:

```powershell
uv run pytest tests/data_platform -q
uv run pytest tests -q
uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
uv run mypy
git diff --check
```

The original runner also prints uv's actual interpreter and preserves pyproject
Python >=3.12, SciPy >=1.14.0 and cryptography >=46.0.0. The repair runner additionally
lints the edit/verifier scripts and checks all repair payload whitespace. Neither
runner discards logs, changes dependencies, stages source or infers a push.

## Honest verification

Executed: five focused sandbox tests passed on Python 3.12.8/DuckDB 1.2.2. They use
real disposable SQL copies, read-only reopen, connection closure and exact temporary
handle rebinding/restoration on normal/error exits; source-edit tests use synthetic
text (not fabricated native dependencies). No successful native numerical result
was mocked. Python compilation, line lengths, whitespace, final ZIP nonempty/CRC/
exact member set/every payload SHA-256 and separate archive SHA-256 are checked.

NOT executed: actual repository checks, the repaired original five boundary cases,
Ruff, mypy, PowerShell/uv or full native/source E2E. Syntax/text-transform/synthetic
SQL verification is NOT full native integration. Native boundary success is NOT
inferred. This fix requires actual local rerun; no test skip, assertion weakening,
tolerance change, fake dependency harness or production workaround is supplied.

No live acquisition, user-data migration/loading/backfill, real authority/key/policy
registration, production publication, trading or cutover occurs. All holds remain.
