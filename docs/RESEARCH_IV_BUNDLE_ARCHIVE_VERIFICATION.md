# Delivery verification: research-IV bundle archive candidate

## Actual repository checks

NONE executed. No access to the Windows checkout, git branch/HEAD, local diff,
uv interpreter, local dependency environment, or current local QA results.
No files were staged, committed or pushed. No newer commit or failure is claimed.
Uploaded snapshot presence is not acceptance of the previous bundle package.

## Focused sandbox checks executed

- Python 3.12.8, DuckDB 1.2.2, Linux sandbox; existing installed pytest.
- 41 focused tests PASSED, zero failures/skips, final run 0.88 seconds.
- 14 parameterized synthetic SQL history cases exercise the actual new `_scope`
  implementation; additional SQL tests cover empty-reader noninitialization,
  dedicated/file-backed target checks, and a quoted catalog alias on a safe filename.
- Remaining tests exercise canonical NEGATIVE assembly records, bounds, explicit
  authority denials, exact reviewed request scopes, prior links and UTC instants.
- Synthetic SQL rows are deliberately populated directly. They do not prove the
  real AuditLedger writer lifecycle, native successful assembly, SciPy computation,
  contract registration, transaction rollback or full archive reader acceptance.
- No substitute native solver, fabricated dependency harness, successful native
  result mock, tolerance relaxation, test skip or dependency downgrade was used.

Invocation was the sandbox interpreter's pytest against only the new record test
file with the new source directory on PYTHONPATH and --import-mode=importlib.
It was NOT `uv run pytest` and NOT tests against a mounted repository.

## Supplied but NOT executed: repository boundary tests

Seven tests reuse uploaded bundle/revalidation/archive fixtures, actual native
assembly/model/Gold SQL and AuditLedger APIs, with the LOWER SOURCE KERNEL
SUBSTITUTED by the existing fixtures. They cover:

1. Successful assembly archive and exact retry preserving original row.
2. Recording review_required without publication.
3. Failure of final audit after domain commit blocking reads and retries.
4. Domain failure rolling back contract, definition, build and attempt.
5. Shared definition origin verified in its original request scope.
6. Duplicate requests rejected before initialization/native work.
7. Distinct cursor on the same live file rejected as archive input/output alias.

They are not full native acquisition-to-bundle E2E, and were NOT run here.
The positive archive-record codec branch and full writer transaction integration
therefore remain locally unverified. No success is inferred from compilation.

## Syntax / archive / checksum verification

All five delivered Python files were compiled with Python's `compile` (no execution
of repository boundary tests). Line length <=100 and trailing-whitespace/newline
checks were performed on delivered Python sources. All payloads were checked for
nonempty content, LF termination and absence of trailing whitespace.

The completed ZIP is verified for nonzero size, archive SHA-256, CRC, nine EXACT
unique members and every one of eight payload SHA-256 checksums. The checksum
manifest excludes itself by design; the separately delivered archive checksum
covers the complete ZIP including that manifest. The standalone archive verifier
is included and is run against the completed delivery. No download URL is invented.

## NOT run

- All five mandatory repository QA commands.
- The previous bundle package's repository boundary tests.
- The seven new repository boundary tests.
- Ruff, mypy, uv, Windows PowerShell runner.
- Supported-runtime native numerical/source integration and full native E2E.
- Live acquisition, user data loading/migration/backfill, production publication,
  trading, decision-loop cutover or real authority registrations.

The QA runner checks the actual branch and explicitly supplied full reviewed HEAD,
reports uv's interpreter, checks unchanged dependency minimums, closes prior bundle
QA first and then runs all required commands. Until those commands actually pass
locally, both dependency acceptance and this archive candidate remain unconfirmed.
