# Plan-first read-only hypothetical spot/vol surface inspection

## Accepted baseline and inspected sources

a400908 is the latest accepted user-reported QA-passed HEAD/origin baseline. 52b1375
is the accepted preceding attribution inspection milestone. No newer failure/commit
was supplied. Actual current surface/native DTOs, coordinate profiles, model/numerical/
boundary tests, original memory/file helper, current fixture tuple and pyproject were
retrieved. Existing sources, formatting fixes, source identity assertions, kernel
settings, bounds, dependencies and tests remain untouched. Repository access is
unavailable; local branch/full HEAD/QA were not independently reproduced. Historical
sandbox limitations do not revoke accepted user repository QA.

## Command boundary and units

- research-iv-spot-vol-surface-inspection@1
- actual service native-research-iv-hypothetical-spot-vol-surface@1

```powershell
uv run python scripts/inspect/inspect_research_iv_spot_vol_surface.py `
  --bronze-db 'C:\synthetic\bronze.duckdb' `
  --frame-silver-db 'C:\synthetic\frames.duckdb' `
  --reference-silver-db 'C:\synthetic\references.duckdb' `
  --assessment-db 'C:\synthetic\assessments.duckdb' `
  --source-gold-db 'C:\synthetic\gold.duckdb' `
  --archive-db 'C:\synthetic\iv-archive.duckdb' `
  --stress-archive-db 'C:\synthetic\stress-archive.duckdb' `
  --stress-record-id-pin '<reviewed-64-character-stress-record-id>' `
  --recording-fingerprint '<reviewed-64-character-full-recording-fingerprint>' `
  --vol-shift-bps -100 --vol-shift-bps 0 --vol-shift-bps 100
```

Example paths are disposable synthetic fixtures, not instructions to load user data.
Add --execute only for explicitly reviewed existing files. The two pins are STRESS
recording ID and full original audit/domain fingerprint, not underlying IV IDs,
native/surface/study fingerprints, Git HEAD or ZIP hash. No caller base IV, spot grid,
terms, source pins/result DTO or latest/fingerprint-refresh path is accepted.

Volatility tokens must already be canonical, sorted, unique integers (1..8 columns,
-5000..5000). No +1, -0, 01, floats, exponents, whitespace, sorting, clipping,
deduplication or implicit zero insertion. 1bp is +0.0001 ABSOLUTE annual sigma;
+100bps means +0.01 sigma (one volatility percentage point), NOT +1% of base sigma.
Frozen spot rows are never supplied or replaced by the CLI.

## Plan mode: no I/O

Without --execute, status is PLANNED. Only bounded literal path/pin/shift validation
and JSON output occur. Supplied paths remain literal/unverified. No Path construction
for arguments, resolving/probing/opening/initialization, network, credentials, DuckDB/
SciPy or native/model imports occur. Plan explicitly says derived_coordinates_checked
False: valid shift TOKENS do not prove derived sigmas fit the unknown original IV
bracket. Exit zero alone is not current verification or pricing. Plan echoes only
caller-supplied literal paths; execution does not echo paths/exceptions.

## Seven existing read-only roles

Every file must exist and every connection opens read_only=True. Supported physical
aliases among first five sources reuse ONE handle, including hardlinks. Member IV
archive differs from all five; stress archive differs from all preceding six. Same
file/hardlink archive aliases reject BEFORE connect. ExitStack closes unique handles
on positive/review/failure, including a corrupt seventh file. No writes, initialization,
adoption, repair, recovery, retry, migration or new audit jobs occur.

Exact native version/context bound and result class are checked. CLI invokes the
ACTUAL accepted native surface service with exact reviewed pins and exact new assumed
vol grid. The service retains all original currentness/archive/source/model gates,
frozen spot grid, exact solved IV and repeated full-grid/context comparisons. A valid
request with any out-of-bracket derived sigma fails closed as sanitized FAILED,
not an accepted subset/column or fabricated review DTO. No bracket expansion/clamping.
Trusted single-owner DB/filesystem conditions remain; file identity checks are not
protection against concurrent privileged rewriting or whole-file rollback/deletion.

## Complete-grid bounded diagnostics

Execution JSON <=16 KiB. Contains exact reviewed pins, requested absolute-vol grid,
status/reason codes, four narrow facts, explicit denials, generic identity/time None,
read_only_execution=True and accepted_surface_summary ONLY on native positive.

Accepted projection reports source/surface fingerprints, original base IV/hex,
volatility profile, actual Python/SciPy labels, frozen spot/vol axes, complete cell
count and <=8 column summaries. Each column retains exact derived volatility Decimal,
model float and hex. It reports minima/maxima of full model price CHANGE and signed
interaction CHANGE across ALL original spot rows, plus maximum absolute reconstruction
roundoff. These extrema are diagnostic selectors, not worst-loss, margin, VaR,
portfolio exposure, accuracy bounds or observed market responses.

Before aggregation, complete Cartesian row-major order, count, uniqueness, column
coordinates, exact supported types, finite values/denials, supported profiles and
canonical surface self-hash are validated. Missing/reordered/duplicate cells or a
bad column reject rather than taking an accepted prefix/subset. Actual coordinate
helper checks decimal/float/hex consistency, not new source/model truth. Min/max
select existing finite unrounded numbers; no repricing, residual threshold, sign
correction or numerical rounding is done by this command. Full raw before/after
native contexts, record_json, all cell/Greek DTOs, provisional surfaces, source data/
tokens/clocks, file paths or arbitrary exception bodies are NEVER dumped on execute.
The summary is not a durable replay artifact or replacement evidence DTO.

Review can retain coherent partial native facts but accepted_surface_summary and
evidence_fingerprint must be None. hypothesis flag is strictly True; endogenous
volatility_response_modelled and portfolio_pnl_asserted remain strictly False even
on positive. Original hypothetical axes do not become authenticated market prices,
canonical identity/binding, authoritative terms, suitability, acquisition authenticity,
availability, historical validity, publication, atomicity or decision eligibility.
All denials remain False and canonical_contract_id/event_ts/published_at stay None.
Original individual clocks remain in actual native evidence, not reinterpreted here.

Exit codes:
- 0 = PLANNED OR computed_current_native_research_iv_spot_vol_surface.
- 2 = review_required OR parser usage error.
- 1 = fixed sanitized IV_SPOT_VOL_SURFACE_INSPECTION_FAILED.
Always inspect status. Repeated observations are not global atomic snapshots or
future-validity guarantees. No accepted partial surface appears on exceptions.

## Verification and fixture integrity

Sandbox tests cover no-I/O plans/import guards, literal paths, pins/vol tokens,
refusal of spot overrides, negative diagnostics/denials, summary limits and actual
new finite min/max selectors. Real disposable DuckDB tests cover every archive alias,
hardlink/source reuse, read-only mode, normal/body-error closure and corrupt-last-file
cleanup. These are NOT BSM pricing or native currentness E2E. No native/model success
or dependency implementation is fabricated, mocked or replicated.

Five repository CLI/native boundary cases are supplied but NOT sandbox-run: actual
accepted exact-vol/column summary with unchanged DB bytes, wrong review pin, changed
source, recorded-review nonpromotion and sanitized post-native exception. They use
actual surface/current/archive/kernel APIs with the original lower source substitute
unchanged. Existing COPY FROM DATABASE helper and seven-handle source binding adapter
are reused unchanged. Original memory owners remain alive; actual file-backed owners
close before read-only reopen. No fake memory filenames, relaxed source identity
assertion, copied success DTO or live-file self-attachment is introduced.
Positive full-surface shape/hash/coordinate/aggregation integration is covered only
by these supplied native cases, NOT claimed as executed here.

Actual repository mandatory QA, Ruff/mypy, Windows runner and full native acquisition
E2E are NOT run. See delivered verification report for executed counts and separate
syntax/whitespace/archive/CRC/exact-member/payload/archive checksum evidence. Uploaded
snapshots are not proof of local HEAD or independently reproduced repository QA.

## Apply and local QA

Verify ZIP with standalone verifier: ZIP path and --sha256 set to the SEPARATE
64-character archive digest, NOT verifier-script manifest hash or 40-character Git
HEAD. Manifest excludes itself; ZIP checksum covers it. Extract to disposable folder,
review additions and copy only where destination does not exist; reconcile collisions
instead of overwriting accepted fixes. No auto-install/staging/commit/push, production
actions or unrelated-log deletion occurs.

Run scripts/inspect/qa_research_iv_spot_vol_surface_inspection.ps1 from repository root
with ExpectedHead = explicitly reviewed FULL 40-character LOCAL git rev-parse HEAD,
not a400908, a filename, evidence fingerprint or ZIP checksum. Runner checks branch/
HEAD, prints uv-selected interpreter, runs ALL five mandatory commands, standalone
verifier lint and additional untracked whitespace checks. Never auto-fill an unreviewed
HEAD or weaken tests/typing/dependencies/bounds to pass QA. Passing this package is
not whole-platform acceptance or permission to lift the data-loading hold.

Real acquisition/loading/migration/backfill, identity/key/policy/authority registrations,
production publication, trading and cutover remain prohibited.
