# Plan-first read-only native spot-stress inspection

## Source reconciliation and acceptance

Latest explicitly reported commit remains ed3f6f7 (HEAD/origin aligned in the last
Git output). User subsequently reported QA/tests and updated sources for the fixed-IV
spot-stress package and requested its commit message. That report is accepted;
no new commit hash, branch state, push or traceback was supplied. Do not invent a
stress-package commit ID or mark accepted user QA as pending. Repository access is
unavailable and no local HEAD/QA was independently reproduced.

Actual current stress numerical/native modules, their input/numerical/boundary tests,
pyproject, existing CLI diagnostic tests and the actual memory fixture snapshot helper
were retrieved. This additive package does not replace accepted sources, overwrite
formatting fixes, change numerical bounds/solvers or rebuild existing fixture data.

## Command boundary

inspection version: research-iv-spot-stress-inspection@1
actual service: native-research-iv-fixed-vol-spot-stress@1

```powershell
uv run python scripts/inspect/inspect_research_iv_spot_stress.py `
  --bronze-db 'C:\synthetic\bronze.duckdb' `
  --frame-silver-db 'C:\synthetic\frames.duckdb' `
  --reference-silver-db 'C:\synthetic\references.duckdb' `
  --assessment-db 'C:\synthetic\assessments.duckdb' `
  --source-gold-db 'C:\synthetic\gold.duckdb' `
  --archive-db 'C:\synthetic\iv-archive.duckdb' `
  --build-id-pin '<reviewed-64-character-IV-build-id>' `
  --archive-fingerprint '<reviewed-64-character-full-archive-fingerprint>' `
  --revalidation-fingerprint '<reviewed-64-character-native-revalidation-fingerprint>' `
  --shock-bps -1000 --shock-bps 0 --shock-bps 1000
```

Example paths are disposable synthetic fixtures, not instructions to load user data.
Add --execute only for an explicitly reviewed existing fixture. No stage/bundle/
recovery-capture fingerprint substitutes for the three actual per-build IV pins.
No caller source/result/terms/IV DTO, latest lookup or pin refresh is supported.

Shock tokens are canonical integers: no +1, 01, -0, whitespace, floats or exponents.
They must already be sorted/unique, 1..16 values within -5000..5000. No sorting,
deduplication, clipping or automatic zero insertion occurs. Zero shock is optional;
the native service always computes an unshocked model baseline separately.

## No-execute plan

Default status is PLANNED. Only bounded literal string/pin/shock validation and JSON
output occur. Supplied paths remain literal/unverified. No Path construction for
arguments, filesystem/DB probing/resolving/opening/initialization, network, credential
lookup, DuckDB/SciPy or native execution import occurs. Exit zero in plan mode is not
source verification or a pricing result. Execution has no hidden default data paths.

## Read-only execution

All SIX database roles must exist. Every connection opens read_only=True. Supported
same-file aliases among the first five roles reuse one actual handle, including
hardlinks; archive must be physically distinct from all five. ExitStack closes all
owned handles on positive/review/failure, including later corrupt-file open failure.
No archive/root initialization, write, migration, audit job, repair or retry occurs.
Native dependency version/bounds and exact result class are gated before projection.

The ACTUAL native spot-stress service performs original source/IV revalidation,
extracts exact spot/terms/IV, reprices the baseline/grid, reruns native revalidation
and recomputes the grid. This CLI never reproduces those native algorithms or
substitutes successful model results. It is a command boundary, not a new trust tier.

## Diagnostic output

Execution summary <=16 KiB. It contains exact reviewed pins, requested shock tuple,
status/reason codes, three narrow native flags, explicit denials, and generic identity/
time fields None. Positive requires all native flags True, valid evidence fingerprint,
an exact typed accepted study matching provisional/repeated studies, and validated
research-only study/runtime/point profiles.

Only positive exposes accepted_study: study fingerprint, fixed IV, actual Python/SciPy
versions, baseline BsmValues, exact derived spot strings and each cell's BsmValues /
model_price_change. All floats remain unrounded. Price change is relative to the
MODEL baseline, not observed premium, executable fill or portfolio P&L. Vega/rho are
per 1.00 absolute unit; theta uses 365 model days. No market volatility-response model
is asserted. Identity, suitability, availability and eligibility stay unverified.

Review output has accepted_study=None and evidence_fingerprint=None, even if native
observations retain provisional/repeated calculations. No nested archive/source/native
DTOs, raw payloads, provisional curve, source tokens, file paths or arbitrary exception
bodies are printed on execution. Original source timestamps remain in the native DTO;
this diagnostic deliberately omits them rather than invent a common economic time.
Plan mode explicitly echoes only the paths the caller supplied.

Exit 0: PLANNED OR computed_current_native_research_iv_spot_stress.
Exit 2: review_required OR argparse usage error.
Exit 1: fixed IV_SPOT_STRESS_INSPECTION_FAILED.
Always inspect status; exceptions never produce a partial accepted curve.

## Tests and honest verification

Focused sandbox tests cover no-I/O plans/import guards, shock parsing, pin/path
validation, negative diagnostic denials, provisional omission and summary limit.
Actual disposable DuckDB tests cover read_only=True, all role alias obligations,
hardlinks, normal/error closure and corrupt-sixth-file cleanup. These are NOT native
pricing/reconciliation E2E. No successful native computations or dependencies were
replicated/mocked. Positive projection is exercised in supplied repository integration
only, through the actual service/kernel.

Four repository boundary cases are supplied: actual positive curve with unchanged DB
bytes, wrong native pin, changed source and sanitized post-native exception. They are
NOT run in the delivery sandbox. They reuse the ACTUAL seven-role COPY FROM DATABASE
helper unchanged and take its first six file paths. Original memory owners stay alive;
actual file-backed archive owners close before read-only reopen. A NEW test-local
six-handle adapter temporarily binds the captured four source roles to actual reopened
handles and restores in finally. The original exact handle-identity assertion remains
untouched. No fake filename for memory DBs or live-file self-attachment is introduced.

Actual repository mandatory QA, Ruff/mypy and full native E2E are NOT run here. The
verification report distinguishes executed focused/synthetic tests, parsing and
archive/checksum checks from unexecuted native cases. Windows PowerShell runner is
supplied, not executed in the Linux sandbox.

## Apply and verify

Verify the original ZIP using the standalone verifier with ZIP path and --sha256 set
to the SEPARATE 64-character archive checksum. A payload manifest's verifier-script
hash is NOT the archive hash. A full 40-character Git HEAD is also NOT a ZIP hash.
Manifest excludes itself; archive checksum includes the manifest. Extract to a
disposable directory, inspect additions and copy only where destinations do not exist.
Reconcile collisions instead of overwriting committed fixes. No auto-installer,
staging, commit, push, unrelated-log deletion or user-data action is included.

Run scripts/inspect/qa_research_iv_spot_stress_inspection.ps1 from repository root.
ExpectedHead is the explicitly reviewed FULL 40-character LOCAL git rev-parse HEAD,
not a short hash, filename or evidence/archive digest. Do not auto-fill an unreviewed
HEAD to bypass the check. Runner checks expected branch/HEAD, shows uv's actual
interpreter and runs all five mandatory QA commands plus untracked whitespace checks.
It never weakens dependencies/tests/assertions or stages unrelated files.

All acquisition/loading/migration/backfill, real identity/key/policy/authority
registration, production publication, trading and cutover remain on hold. This package
adds no decision admission, recovery authority, governance identity or publication.
Passing local QA is not whole-platform acceptance or permission to load user data.
