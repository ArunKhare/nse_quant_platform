# Delivery verification: archived research-IV bundle current-source revalidation

## 1. Actual repository checks

None executed by the assistant. No access to C:\Projects\nse_quant_platform, local
HEAD/branch/status, uv interpreter, local dependencies or full repository tree.
No staging, commit, push, native data loading or publication occurred.

User reports c9c6c42 at HEAD and origin/feat/medallion-feature-store, with QA/tests
passed for the prior archive package. This is the latest accepted user-reported
baseline; it is NOT incorrectly left unconfirmed. No newer commit is invented.
This NEW package has no user-reported local QA/commit confirmation yet.

## 2. Focused sandbox tests executed

Python 3.12.8, installed pytest, Linux sandbox. 39 tests passed, zero skipped or
failed. Invocation used the sandbox interpreter against ONLY the new observation
test file, with the new source directory on PYTHONPATH and --import-mode=importlib.
It was not uv and not a mounted actual repository.

- 30 cases cover exact bytes/all pairwise equality orderings, immutable input
  types, bounded payloads, no metadata/float/whitespace normalization, ordered
  negative retention, digest role binding, and service API/default denial flags.
- Nine synthetic ZIP cases cover valid integrity, wrong archive/payload checksums,
  extra/missing members, duplicate manifest entries, empty payload, whitespace
  failure and CRC corruption.

Equal arbitrary synthetic bytes are explicitly tested as ONLY byte equality; they
are not native successful assembly fixtures. The service's native call path was
NOT executed by these tests. No successful native computation was mocked. No
fabricated dependency harness, dependency downgrade, native replica, test skip,
weakened bound or tolerance relaxation was used.

## 3. Synthetic SQL / mocked-boundary integration

No SQL or native boundary integration tests were executed in this delivery sandbox.
Fourteen repository boundary cases are supplied, reusing inspected actual
archive/assembly/per-build revalidation/model/Gold fixtures. The existing LOWER
SOURCE KERNEL IS SUBSTITUTED. They are not full acquisition-to-revalidation E2E.

They cover positive exact full-record reproduction and no audit/domain writes;
wrong reviewed pin; superseded successful and recorded-review heads; changed
sources; both negative orderings; exact bundle archive retry between assemblies;
failed/incomplete pending origin obligations before and after; native exception;
read-only archive handle; same-live-file cursor alias rejection; frozen member
review fingerprints after member-archive retry; and native resource exhaustion.

These fourteen cases were NOT run by the assistant. Native service control flow,
actual successful archive/current-result matching, all supplied fixture interfaces,
read-only integration, audit invalidation and alias integration remain to be
verified against the actual supported local repository environment.

## 4. Syntax / archive / checksum verification

All five delivered Python files compile. No boundary test execution is inferred
from compilation. Delivered Python line lengths <=100; all payloads are nonempty,
LF-terminated and free of trailing whitespace. The embedded Python runtime and
whitespace snippets in the PowerShell runner compile; this does NOT establish
PowerShell syntax, native argument passing, uv execution or runner success.

Completed ZIP verification checks nonzero size, full archive SHA-256, CRC, EXACT
nine unique members, and all eight payload SHA-256 checksums. The manifest excludes
itself; the separate ZIP checksum covers every ZIP byte, including the manifest.
The standalone verifier is executed against the actual completed ZIP. Archive
integrity is not authenticated provenance, Git evidence or native/source proof.

## 5. Not run

- uv run pytest tests/data_platform -q
- uv run pytest tests -q
- uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
- uv run mypy
- git diff --check
- Windows PowerShell runner; Ruff/mypy themselves; supported-dependency numerical
  integration; full native E2E/integrated operational acceptance.

The supplied runner requires a reviewed full 40-character local Git HEAD, confirms
branch/HEAD and ancestry from c9c6c42, reports uv's actual interpreter, respects the
uploaded Python/SciPy/cryptography bounds, verifies delivered hashes, runs focused
and mandatory QA and checks untracked payload whitespace. It does not install a
substitute runtime, weaken QA, stage source or discard unrelated logs.

No live acquisition, user loading/migration/backfill, actual identity/key/policy/
authority registration, production publication, trading or decision cutover was
executed. All those holds remain in place after this candidate delivery.
