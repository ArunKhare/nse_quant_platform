# Plan-first read-only current stress-archive inspection

## Baseline and source reconciliation

Last user-supplied Git output still shows f52095e at local HEAD/origin. The user also
separately confirmed current stress-archive revalidation QA/tests passed. That report
is accepted, but no newer commit or push is confirmed by the repeated Git output.
Do not invent a revalidation commit ID, infer discarded work or mark its user QA as
unconfirmed. Repository access remains unavailable; local branch/HEAD/QA were not
independently reproduced. No newer failure was supplied.

Actual current revalidator, comparison module, native archive, stress CLI, boundary
fixtures, seven-role memory/file helper and pyproject were retrieved. This additive
package does not overwrite any accepted source/formatting fix, weaken assertions,
change dependencies/bounds/numerical settings or reconstruct prior generated modules.

## Purpose and API boundary

The accepted current stress-archive API reconstructs frozen inputs, runs two actual
native stress observations, compares complete retained bytes and rereads the original
audit evidence. This CLI makes that operation safely inspectable; it does not create
a new trust tier, implement alternative pricing or replace those native checks.

- research-iv-current-stress-archive-inspection@1
- actual service research-iv-spot-stress-archive-current-revalidation@1

```powershell
uv run python scripts/inspect/inspect_research_iv_current_stress_archive.py `
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

Example paths are disposable synthetic fixtures, not instructions to load user data.
Add --execute only to inspect explicitly reviewed existing fixture files. The two pins
are the STRESS recording ID and its full original domain/audit fingerprint, not an
underlying IV ID, native/study fingerprint, stage ID, Git HEAD or ZIP digest.
No caller shock grid, replacement native pins, terms, IV/spot, verified/result/study
DTO, latest lookup or automatic pin refresh is accepted. Frozen inputs remain solely
owned by the actual verified recording/native service.

## Plan mode: no I/O

Without --execute, status is PLANNED. Only bounded literal string/pin validation and
JSON output occur. Supplied paths remain literal/unverified: no Path construction for
arguments, resolving/probing/opening, database/file creation, initialization, network,
credential lookup, DuckDB/SciPy or execution-service imports occur. Exit zero does not
mean sources were checked or a study was computed. All seven paths must be explicit.

## Execution: seven existing read-only roles

All seven files must exist. Every connection opens read_only=True. Supported physical
aliases among first five roles reuse ONE handle, including hardlinks. Member IV archive
is distinct from all five; dedicated stress archive is distinct from all six preceding
roles. Same-file/hardlink aliases are rejected before connect. No adoption, repair,
initialization or source write is attempted. ExitStack closes unique owned handles on
positive/review/failure, including corrupt seventh-file open failure.

Exact service version/bounds and exact typed native result are checked. CLI passes
reviewed record ID/fingerprint unchanged to the ACTUAL revalidator. Reader transactions,
current source/kernel work, frozen-grid reconstruction, recorded-review gate and
complete observation/audit comparisons remain the service's existing responsibilities.
Trusted single-owner DB/file conditions remain; file identity checks do not protect
against concurrent privileged replacement or whole-file rollback/deletion.

## Bounded diagnostic contract

Execution output <=16 KiB. Contains only versions, status/reason codes, exact reviewed
record pins, five narrow flags, explicit research denials, generic identity/time None,
read_only_execution=True and accepted evidence IDs/study metadata on positive.
Positive requires all flags True, valid native/evidence IDs, a typed research-only
study and supported bounded metadata. Metadata includes study fingerprint/version,
original frozen shock tuple and actual Python/SciPy runtime labels. No numerical
curves, exact spot/terms, original record_json, source payloads/tokens/paths, before/
after archives, fresh native DTOs, comparisons or arbitrary exception bodies are
printed on execution. Plan mode explicitly echoes caller-supplied literal paths.
The metadata is diagnostic, not a retained replay artifact or replacement evidence DTO.

Review may retain coherent partial facts (e.g. model/recording reproduction before
an after-audit failure) but accepted_study_metadata/native_stress_fingerprint/
evidence_fingerprint MUST be None. Integer booleans, inconsistent fact dependencies,
unknown versions, duplicate/malformed reason codes or authority escalation fail closed.

Exit codes:
- 0: PLANNED OR matched_current_research_iv_spot_stress_archive.
- 2: review_required OR argparse usage error.
- 1: fixed sanitized IV_CURRENT_STRESS_INSPECTION_FAILED.
Always inspect status. No accepted partial study appears on an exception.

The current_source_checked flag on a review indicates current-native checks were
invoked/returned, not that all sources/grids were accepted. Positive additionally
requires model_computation_rechecked, exact_recording_reproduced and stable original
audit evidence. No rounding, tolerance-based comparison or later-good selection occurs.
Retained complete native stress bytes really exist; comparing them is not a claim to
reconstruct unretained provider originals, prove historical economic/availability time,
authenticate issuers or establish complete decision replay/global atomic snapshots.

No portfolio P&L, market volatility-response forecast, canonical underlying identity,
model suitability, acquisition authenticity, availability, historical validity,
publication, atomicity or decision eligibility is established. All corresponding
flags stay False; generic canonical_contract_id/event_ts/published_at remain None.
Source clocks remain in actual native DTOs; the diagnostic omits them, never inventing
a common economic time. No new admission, recovery or trading contract is added.

## Verification and fixture integrity

Focused sandbox tests cover no-I/O plan/import guards, exact pins/path bounds, refusal
of caller shock overrides, negative summaries, strict denials/partial facts and output
bounds. Actual disposable DuckDB tests cover all role aliases/hardlinks, seven existing
read-only handles, reuse and closure, corrupt-last-file cleanup and body errors.
These are focused/synthetic I/O tests, NOT native pricing/revalidation E2E. No model/
native dependency implementations or successful native computations are fabricated.

Five actual repository CLI/native boundary tests are supplied but NOT sandbox-run.
They reuse the existing seven-role COPY FROM DATABASE helper unchanged for the original
bundle fixture, retain first six source/member-archive paths, then use the ACTUAL
file-backed stress archive as seventh and close its owner before read-only reopen.
The existing seven-handle bind_fixture_sources adapter is reused unchanged. It
preserves the four source-role identity assertions and restores original memory owners
in finally. No fake filenames for memory DBs, weakened assertion or live-file
self-attachment is introduced. Lower source substitution is unchanged; these cases
are not full acquisition-native E2E.

Mandatory repository QA, Ruff/mypy, Windows PowerShell execution and full native E2E
were NOT run here. See delivered verification report for executed counts and separate
syntax/whitespace/archive/member/checksum checks. User acceptance of the prerequisite
revalidator remains valid and is distinct from this delivery's unrun repository QA.

## Apply and QA

Verify ZIP using standalone verifier with ZIP path and --sha256 set to the SEPARATE
64-character archive checksum, never a verifier-script manifest hash or a Git HEAD.
Manifest excludes itself; separate whole-ZIP checksum includes manifest. Extract to
disposable folder, review additions and copy only where destination does not exist.
Reconcile collisions rather than overwrite committed fixes. No auto-installation,
git staging/commit/push or unrelated-log deletion is included.

Run scripts/inspect/qa_research_iv_current_stress_archive_inspection.ps1 from repository
root. ExpectedHead is explicitly reviewed FULL 40-character LOCAL git rev-parse HEAD,
not f52095e, a filename, evidence fingerprint or ZIP digest. Runner checks branch/HEAD,
reports uv's actual interpreter, runs ALL five mandatory QA commands, lints standalone
verifier and checks additional untracked whitespace. Do not auto-fill an unreviewed
HEAD or weaken tests/typing/dependencies/bounds to pass QA.

Live acquisition, user-data loading/migration/backfill, actual identity/key/policy/
authority registrations, production publication, trading and cutover remain on hold.
Passing this package is not whole-platform acceptance or permission to load user data.
