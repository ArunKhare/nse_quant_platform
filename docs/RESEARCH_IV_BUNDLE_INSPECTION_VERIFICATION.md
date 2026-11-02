# Inspection candidate delivery verification

## 1. Actual repository

No checks executed against C:\Projects\nse_quant_platform. No independent branch,
HEAD, origin, local uv interpreter/dependencies or full repository QA access.
User reports local HEAD 092d936 and QA/tests passed. User's origin remains c9c6c42;
092d936 is NOT described as pushed. No newer commit or failure is invented.
This new inspection candidate has not been locally accepted or committed.

## 2. Focused sandbox

39 tests passed, zero failures/skips, Python 3.12.8 and DuckDB 1.2.2 in Linux.
Invocation used sandbox Python pytest against only the new CLI test module with
the new source directory on PYTHONPATH and --import-mode=importlib. Not uv and
not a mounted actual repository. Ruff and mypy were unavailable/not executed.

Tests cover nonexecuting plan with file/path probes and execution imports forbidden,
literal-path preservation, pin/path bounds, missing-file noncreation, sanitized
filesystem failures and bounded negative diagnostic projections. Diagnostic-only
SimpleNamespace fixtures are negative/malformed states, NOT successful native
computations or substitute native dependencies.

## 3. Synthetic SQL and native boundary distinction

Sandbox tests use REAL disposable DuckDB databases/connections for seven read-only
handles, write rejection, closure, supported same-file/hardlink source alias reuse,
archive/source separation and cleanup after a corrupt later database fails to open.
They instrument actual connect calls, not a replicated database or native solver.
Synthetic tables/file fixtures do NOT establish native analytics/source truth.

Five supplied repository boundary tests call the actual inspection CLI and existing
service against re-opened READ-ONLY actual fixture databases. They cover positive
reproduction with unchanged database-file hashes, wrong reviewed fingerprint,
changed source, pending archive-origin obligation, and sanitized service failure.
They reuse actual audit/archive/Gold/model fixtures with LOWER SOURCE KERNEL
SUBSTITUTED. They are NOT full acquisition-to-inspection E2E and were NOT run here.

No successful native computation was mocked. No tests skipped, dependency replica,
weakened assertion/bound/tolerance, or pyproject change was used. Actual service
integration, Windows hardlink/filesystem behavior and supported native numerical
execution remain to be verified locally.

## 4. Syntax / integrity

All five delivered Python files compile. Python line lengths <=100, nonempty
LF-terminated payloads and no trailing whitespace are checked. Embedded Python
snippets in the PowerShell runner compile; this is NOT PowerShell execution or
native-argument compatibility verification.

The completed ZIP is verified nonempty with valid CRC, EXACT nine unique members,
every one of eight payload SHA-256 checksums and a separate full archive SHA-256.
The manifest excludes itself; the archive hash covers the ZIP including manifest.
The standalone verifier is also executed on the actual completed ZIP.
No download URL, Git action, QA pass or native computation is fabricated.

## 5. Not run

- uv run pytest tests/data_platform -q
- uv run pytest tests -q
- uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
- uv run mypy
- git diff --check
- New five repository/native-boundary cases, Windows PowerShell/uv, supported full
  numerical/source integration, native E2E and operational platform acceptance.

The supplied PowerShell runner verifies reviewed full HEAD/branch/092d936 ancestry,
reports uv's real interpreter and dependency minimums, runs focused and mandatory
QA and added/untracked whitespace checks. It does not assume push state, auto-stage,
repair source, change dependencies or delete unrelated logs.

No live acquisition, user loading/migration/backfill, actual key/identity/policy/
authority registration, production publication, trading or cutover occurred.
