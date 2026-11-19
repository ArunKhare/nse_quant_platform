# Research-IV artifact materialization delivery verification

## 1. Actual repository checks

None executed. No direct Windows checkout/branch/HEAD/dependency access, no Git
stage/commit/push. User reports 64ec9b6 at HEAD and origin with QA/tests passed;
that is the latest accepted user-reported baseline, closing the inspection repair.
The new artifact package is a candidate with no local acceptance confirmation.

## 2. Focused sandbox execution

Python 3.12.8, installed pytest, Linux sandbox: 28 focused tests passed with zero
failures/skips. Run only against the new file/API-default test module with its
source directory on PYTHONPATH and --import-mode=importlib. Not uv and not a
mounted repository or supported complete dependency environment.

Real filesystem operations over SYNTHETIC PINNED BYTES cover: write/reread,
no overwrite or adoption, original inode/mtime preservation, explicit new root,
missing-parent refusal, byte/pin/mutability/count bounds, foreign/crash-pending
content rejection, directory/redirect refusal, mutation detection, unsupported-link
and fsync failure, post-link error leaving unadoptable final artifact, competing
final-file race, opened-inode change, and lazy native API/default-denial structure.

The low-level file API checks exact hash/bounds only. Its arbitrary byte fixtures
are NOT research manifest/source/numerical proof. No native successful computation
was mocked, dependency replica installed, skip added or tolerance weakened.

## 3. Native boundary cases supplied, not executed

Ten repository cases reuse actual archive/current bundle revalidation/model/Gold
fixtures, with the existing LOWER SOURCE KERNEL SUBSTITUTED. They cover matching
canonical materialization with two real revalidations/no database writes; existing
file retry refusal; three reviewed-pin mismatches; before-source rejection;
after-source rejection retaining the artifact and both observations; second-call
exception orphan; root/database separation; and archive-retry invalidation.

These ten cases were NOT run here. They are NOT acquisition-to-materialization E2E.
The native materializer's actual service integration, source fingerprints, full
supported numerical dependencies and Windows filesystem behavior remain locally
unverified. Existing in-memory sources stay in memory in these tests; they are not
incorrectly assumed to have file paths, and no read-only fixture reopen is invented.
No inspection helper or committed repair is replaced.

No SQL/native integration was executed in the sandbox. File tests and compilation
are not substitutes for those integration cases or actual supported native E2E.

## 4. Syntax / archive / checksum verification

All five delivered Python files compile, line length <=100, payloads nonempty,
LF-terminated and free of trailing whitespace. Embedded runtime/whitespace Python
in the QA runner compiles. PowerShell syntax/execution and native argument passing
were NOT verified by this Python syntax check.

Completed ZIP is verified nonempty, CRC-valid, EXACT nine unique members with all
eight payload SHA-256 checksums and separate full archive SHA-256. The manifest
excludes itself; the archive checksum includes every ZIP byte and the manifest.
The standalone verifier is executed on the completed archive. No download URLs,
repository writes, QA success, native calculations or governance claims are invented.

## 5. Checks not run

- uv run pytest tests/data_platform -q
- uv run pytest tests -q
- uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
- uv run mypy
- git diff --check
- Windows PowerShell/uv, Ruff/mypy, all native boundary cases, complete native E2E,
  crash-durability/hostile-writer security and operational platform acceptance.

The included PowerShell runner checks actual branch and reviewed full HEAD/64ec9b6
ancestry, reports uv's real interpreter/installed dependency minimums, runs focused
and mandatory QA, additionally lints the archive verifier and checks all delivered
untracked whitespace. It neither installs substitute dependencies nor discards
logs, stages files or commits/pushes.

File materialization remains NOT audited staging or eligible publication. Even a
matching result has audited_stage_recorded=False; visible files are unbound. No
acquisition, user loading/migration/backfill, real authority/key/policy/identity
registration, production publication, trading or cutover was executed.
