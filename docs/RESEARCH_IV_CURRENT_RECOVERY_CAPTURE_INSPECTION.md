# Plan-first read-only inspection of current research-IV recovery captures

## Accepted baseline and source reconciliation

Latest accepted LOCAL commit is 65e3c28, user-reported all QA/tests passed. The user's
Git output places origin/feat/medallion-feature-store at 831fc82, not 65e3c28. Push
of 65e3c28 is not confirmed. Both accepted capture and revalidator QA reports remain
accepted; old delivery docs saying sandbox/native tests were not run are historical.
No newer failure or commit was supplied. Repository access is unavailable; branch,
full local HEAD and QA are not independently verified here.

Actual updated revalidation/observation modules, current boundary fixtures, the
current-stage inspection implementation/entry script, and pyproject were retrieved.
Formatting fixes in the updated sources remain untouched. No old generated payload
replaces a committed fix. This is a new additive module, script, tests and docs.

## Why an inspection CLI

The accepted native service is operational through a Python API. This package adds
a safe plan-first command boundary: actual read-only DB opening, bounded root
metadata preflight, exact reviewed pins, sanitized fixed failures and a bounded
summary of the actual service result. It does not create another verification tier,
change native evidence semantics, or wrap a digest comparison in a new trust claim.

- inspection version: research-iv-current-recovery-capture-inspection@1
- actual service: research-iv-recovery-capture-current-reconciliation@1

## Command

```powershell
uv run python scripts/inspect/inspect_research_iv_current_recovery_capture.py `
  --staging-db 'C:\synthetic\first-stage.duckdb' `
  --capture-db 'C:\synthetic\recovery-capture.duckdb' `
  --artifact-root 'C:\synthetic\artifacts' `
  --capture-build-id-pin '<reviewed-64-character-capture-build-id>' `
  --capture-fingerprint '<reviewed-64-character-full-capture-fingerprint>'
```

Paths above are examples, not instructions to load user data. Use disposable
synthetic fixtures until native platform acceptance gates are complete.
Add --execute only to perform read-only inspection of existing reviewed fixtures.
No stage ID, stage fingerprint or native plan DTO is accepted as a replacement for
what the actual reviewed capture freezes. No pin refresh or latest lookup occurs.
The capture fingerprint is the full original capture reader's evidence fingerprint,
not the nested plan fingerprint, stage fingerprint, feature bundle ID or ZIP digest.

## Plan mode: strict no execution

Without --execute, status is PLANNED and literal supplied strings are retained.
Only argument string/pin validation and JSON output occur. No Path construction for
arguments, resolving, probing, DB/file/root initialization, network, credential
lookup, native service imports or DuckDB imports occur. A path such as a literal
relative/../missing path remains untouched and unverified. Plan success is not
input validation or current reconciliation acceptance.

## Execute mode

Requires TWO existing physically distinct database files, existing recorded absolute
artifact root, and exact reviewed capture pins. All connections open read_only=True.
Same-file and hardlink DB aliases are rejected before connect. Root redirects,
parent junctions/symlinks, DB/root overlap and root entries hardlinked to either DB
are rejected. Metadata preflight is bounded to 256 entries using lazy scandir, reads
no artifact/foreign/pending bodies and rejects entry redirects before following them.
Missing files/root are never created. No directory adoption, cleanup or repair occurs.

ExitStack closes both handles on success, review or error, including corruption
while opening the second file. Native version and exact result type are checked.
The CLI calls the ACTUAL accepted revalidator with the reviewed pins unchanged.
It does not reproduce or replace pricing, stage/audit verification, inventory or
byte comparisons. Existing native limits remain intact.

Preflight is intentionally stricter than direct native early-review handling: CLI
execution requires existing safe input files/root even when the original captured
plan was review_required. It does not bypass I/O checks to obtain a review result.
A valid existing root with foreign/pending content is not read by preflight; actual
stage/native checks may fail closed and produce sanitized FAILED, not an invented
review summary. Use the independent inventory for redacted root diagnostics.
Trusted single-owner DB/root conditions remain; repeated metadata checks are not
protection against privileged or hostile concurrent path rewriting.

## Bounded diagnostic contract

Summary is <=16 KiB and contains only versions, exact reviewed capture pins, status,
bounded reason codes, narrow flags, accepted evidence IDs on positive, explicit
denials, None identity/time fields and read_only_execution=True.
No nested capture record JSON, before/after plans, inventory rows, file names, source
payloads or arbitrary exceptions are printed. Explicit plan mode does echo the paths
the user supplied; execution output does not echo path/exception details.

Positive requires actual matched_current_research_iv_recovery_capture plus all four
narrow flags True and valid plan/evidence fingerprints. Review may retain coherent
partial facts but must expose no accepted plan/evidence IDs. Duplicate/malformed
reason codes, integer booleans, unknown versions or authority escalation fail closed.

Exit codes:
- 0: PLANNED OR explicit matched_current_research_iv_recovery_capture.
- 2: review_required OR argparse usage error.
- 1: fixed sanitized IV_CURRENT_RECOVERY_CAPTURE_INSPECTION_FAILED.
Always inspect status. Exit zero alone does not mean native work ran.

## Evidence boundaries

Even positive current_source_checked is FALSE: no pricing/source-Gold currentness is
checked here. Retained complete PLAN bytes can be compared directly; their internal
original stage/inventory DTOs only had stored digests, not full original replay bytes.
No orphan determination, destruction, adoption, retry, recovery execution, canonical
identity, model suitability, acquisition authenticity, availability, historical
validity, publication, global atomicity or decision eligibility is granted. All
corresponding flags stay false; canonical_contract_id/event_ts/published_at stay None.

## Verification and installation

Sandbox tests cover no-I/O plans, validation, summary contracts, real disposable
DuckDB read-only opens and closure, physical aliases/hardlinks, root preflight,
corrupt-second-file handling and sanitized filesystem failures. These are focused
and synthetic DB/filesystem tests, NOT native reconciliation E2E. Diagnostic shape
fixtures do not stand in for successful native computations.
Five repository integration tests use ACTUAL capture, stage, plan, revalidator and
CLI over actual existing file-backed stage/capture fixtures. They close owning
connections before reopening read-only. No memory source is assigned a fake filename;
no source identity assertion is removed/adapted. The existing lower source substitute
used to create synthetic fixtures remains unchanged. These tests are supplied but
NOT sandbox-executed and are not full acquisition-native E2E.

No actual repository QA was executed; Ruff/mypy are unavailable here. See delivered
verification report for executed focused test count and archive/checksum checks.
Payload syntax/whitespace checks are not full native E2E or lint/type verification.

Verify the ZIP with the standalone verifier (ZIP path and --sha256 with the separate
64-character archive digest). The manifest excludes itself; the archive digest covers
all ZIP bytes including manifest. Extract into a disposable directory, inspect each
addition and copy only if its destination does not exist. Reconcile collisions rather
than overwrite committed fixes. No auto-installer or git staging/commit/push occurs.

Run scripts/inspect/qa_research_iv_recovery_capture_inspection.ps1 from the repository.
ExpectedHead is the explicitly reviewed FULL 40-character LOCAL git rev-parse HEAD,
not 65e3c28, a filename, evidence fingerprint or archive checksum. Runner checks
expected branch/HEAD, reports the uv-selected interpreter, runs ALL five mandatory
QA commands, checks the standalone verifier and additional untracked whitespace.
It never stages unrelated files, discards logs, weakens tests or changes dependencies.
Passing this package is not whole-platform acceptance or permission to load data.

Live acquisition, user loading/migration/backfill, real identity/key/policy/authority
registration, production publication, trading and cutover remain on hold.
