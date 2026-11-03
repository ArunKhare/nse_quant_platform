# Plan-first read-only native delta/gamma attribution inspection

## Accepted baseline and sources

859bd27 is the latest accepted user-reported QA-passed HEAD/origin baseline. 581c319
is the preceding accepted current stress-archive inspection milestone. No newer
failure/commit was supplied. Actual current attribution numerical/native modules,
explicit Decimal profile, native tests, current archive CLI/fixture patterns, memory
snapshot helper and pyproject were retrieved. Existing formatting fixes, arithmetic,
contexts, bounds, assertions, tests and dependencies remain untouched. Repository
access is unavailable; local Git/QA were not independently reproduced. Historical
sandbox limitations do not retract the user's accepted repository QA report.

## New command boundary

inspection version: research-iv-stress-attribution-inspection@1
actual native service: native-research-iv-stress-delta-gamma-attribution@1

```powershell
uv run python scripts/inspect/inspect_research_iv_stress_attribution.py `
  --bronze-db 'C:\synthetic\bronze.duckdb' `
  --frame-silver-db 'C:\synthetic\frames.duckdb' `
  --reference-silver-db 'C:\synthetic\references.duckdb' `
  --assessment-db 'C:\synthetic\assessments.duckdb' `
  --source-gold-db 'C:\synthetic\gold.duckdb' `
  --archive-db 'C:\synthetic\iv-archive.duckdb' `
  --stress-archive-db 'C:\synthetic\stress-archive.duckdb' `
  --stress-record-id-pin '<reviewed-64-character-stress-record-id>' `
  --recording-fingerprint '<reviewed-64-character-full-recording-fingerprint>'
```

Example paths are disposable synthetic fixtures, not permission to load real data.
Add --execute only for existing explicitly reviewed fixture files. The two pins
identify the original stress recording and full original audit/domain fingerprint,
not an IV build, study/native/attribution fingerprint, Git HEAD or ZIP digest.
No caller coefficients, shock grid, terms, IV, spot, native input pins/result/study
DTO, latest lookup or automatic fingerprint refresh is accepted.

## Default no-I/O plan

Without --execute, status is PLANNED and paths remain literal/unverified. Only
bounded string/pin checks and JSON output occur. No Path construction for arguments,
filesystem/DB probing, resolving, opening/initializing, network, credential lookup,
DuckDB/SciPy or native attribution/model imports happen. Exit zero is not source
verification, current model acceptance or a computed attribution. Plan output echoes
caller-supplied paths explicitly; execute output does not echo paths/exceptions.

## Seven existing read-only roles

Every file must already exist. Every connection opens read_only=True. Supported
physical aliases among first five source roles reuse ONE actual handle, including
hardlinks. Member IV archive differs from all five; stress archive differs from all
six preceding roles. Same-file/hardlink archive aliases are rejected before connect.
ExitStack closes unique owned handles on positive/review/failure, including a corrupt
seventh-file opening. No data/contract/audit write, initialization, adoption, cleanup,
repair, retry or new publication is performed. File identity is not a hostile-writer
or privileged-SQL security boundary; trusted single-owner conditions remain required.

Actual native version/context bound and exact result class are checked before output.
The ACTUAL native service still brackets attribution with two complete current
archive-revalidation contexts, requiring complete context and repeated attribution
byte equality. This CLI performs no repricing, Taylor arithmetic or source/evidence
replacement. It validates accepted output structure/hash/finite values for bounded
diagnostic projection, not as a new mathematical or trust verification tier.

## Output and mathematical meaning

Execution JSON <=16 KiB. Contains exact reviewed pins, versions, status/reason codes,
four narrow native facts, explicit research denials, generic identity/time None,
read_only_execution=True and accepted attribution projection ONLY on positive.
Positive requires all four facts True, valid native evidence ID, matching accepted/
provisional/repeated attribution objects, actual typed research attribution, supported
method/Decimal profile and matching canonical attribution self-hash.

Accepted projection includes original source study fingerprint/SHA, actual source
Python/SciPy labels, actual attribution Python label, fixed method/Decimal profile,
and <=16 points. Each point prints shock bps, exact Decimal dS, full model price
change, baseline delta contribution, half-gamma contribution, delta/gamma estimate,
delta-only residual, second-order residual and reconstruction roundoff. No float is
rounded, clipped or corrected to zero. No residual threshold chooses success.

Baseline delta/gamma are unshocked absolute-spot derivatives; this is NOT attribution
using changed Greeks, percentage deltas, a volatility move, theta/rho/vega term or
portfolio position/lot-size accounting. Full BSM model change remains the reference,
not replaced by the Taylor approximation. Residuals include omitted higher-order
behavior AND floating/coordinate effects; they are NOT rigorous error bounds.
Reconstruction roundoff is separate and may be nonzero. Repeated native/arithmetic
results do NOT certify approximation quality. approximation_accuracy_certified and
portfolio_pnl_asserted are ALWAYS False, including zero-shock/zero-residual cases.

Review output has accepted_attribution=None and evidence_fingerprint=None. Valid
partial source/model facts can remain True; a provisional attribution is NEVER
printed. No full before/after native contexts, retained record JSON, source payloads,
provider tokens, source clocks, raw study DTOs, arbitrary exception bodies or original
unprojected decompositions are dumped. The projection is diagnostic only, not a
retained replay artifact or replacement verified DTO. Source clocks remain unchanged
in the native object; no generic economic/publication clock is inferred.

Exit codes:
- 0 = PLANNED OR computed_current_native_research_iv_stress_attribution.
- 2 = review_required OR argparse usage error.
- 1 = fixed IV_STRESS_ATTRIBUTION_INSPECTION_FAILED.
Inspect status, not exit zero alone. Exceptions never produce accepted partial output.

Volatility response, canonical identity/binding, model suitability, authenticated
acquisition, availability, historical validity, publication, atomicity and decision
eligibility remain false/None. Byte integrity/hash checks and repeated observations
are not issuer authentication, global snapshots, future validity or complete historical
provider/decision replay. No native strategy admission/trading authority is added.

## Verification and fixture integrity

Sandbox-focused tests cover no-I/O plans/import guards, input pins/path bounds,
refusal of caller replacement coefficients/grid/pins, strict denials and malformed
negative output, provisional omission and summary limit. Actual disposable DuckDB
checks cover all archive alias obligations, source alias reuse/hardlinks, read-only
handles, normal/body-error closure and corrupt-last-file cleanup. No successful
native/model computation or dependency implementation is mocked/replicated.
Positive attribution projection is exercised only by the supplied repository-native
integration test, not fabricated by a sandbox harness.

Five native repository CLI cases are supplied but NOT run here: actual accepted
component/residual output with unchanged DB bytes, wrong review pin gate, changed
source, recorded-review nonpromotion and sanitized post-native exception. They use
ACTUAL model/current archive/attribution services with the existing lower source
substitute unchanged. Existing COPY FROM DATABASE helper and seven-handle binding
adapter are reused unchanged. Original memory owners remain available and source
identity assertions are restored in finally; no fake memory filenames, removed
assertion, native calculation substitute or live-file self-attachment is introduced.
These tests are not acquisition-native E2E.

Actual repository mandatory QA, Ruff/mypy, PowerShell execution and full native E2E
were NOT run here. See verification report for executed counts and separate parsing/
whitespace/CRC/exact-member/payload/archive-checksum checks. This delivery does not
claim uploads prove local HEAD or successful QA.

## Apply and local QA

Verify ZIP via standalone verifier with ZIP path and --sha256 set to the SEPARATE
64-character archive checksum, NOT a script payload hash in the manifest or Git HEAD.
Manifest excludes itself; whole-ZIP checksum includes it. Extract into a disposable
folder, inspect additions and copy only if destinations do not exist. Reconcile
collisions rather than overwrite accepted fixes. No auto-installation, git staging/
commit/push, production action or unrelated-log deletion is included.

Run scripts/inspect/qa_research_iv_stress_attribution_inspection.ps1 from repository
root with ExpectedHead = explicitly reviewed FULL 40-character LOCAL git rev-parse
HEAD. It is NOT 859bd27, a filename, evidence fingerprint or ZIP digest. Runner checks
branch/HEAD, prints uv's actual interpreter and runs ALL five mandatory commands,
standalone verifier lint and additional untracked whitespace checks. Never auto-fill
an unreviewed HEAD or weaken tests/typing/dependencies/bounds to pass QA.

Real acquisition/loading/migration/backfill, identity/key/policy/authority registrations,
production publication, trading and cutover remain prohibited. Package QA is not
whole-platform acceptance or permission to load user data.
