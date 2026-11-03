# Exact current native revalidation of a reviewed stress recording

## Accepted baseline and source reconciliation

f52095e is the latest accepted user-reported commit, all QA/tests passed, with HEAD
and origin/feat/medallion-feature-store aligned. No newer failure/commit was reported.
The current archive/record codec, complete native stress service and archive fixtures
were retrieved, including current schema/DTOs/bounds. No stale generated module is
substituted. Existing accepted numerical, native, archive and CLI sources remain
unchanged; this is additive. Repository access is unavailable, so local branch/full
HEAD/QA were not independently reproduced. Historical delivery verification statements
are not current claims that the accepted archive remains unconfirmed.

## Purpose

The archive reader verifies ORIGINAL recording obligations but does not revisit
sources/model computation. This package performs ACTUAL fresh native stress work and
compares COMPLETE current observations to the retained bytes. It does not relabel
archived integrity, compare only IV/grid values, or trust a caller's result DTO.

Versions:
- research-iv-stress-archive-observation@1 (bounded pure full-byte comparison)
- research-iv-spot-stress-archive-current-revalidation@1 (native read-only service)

```python
revalidate_research_iv_spot_stress_archive(
    bronze, frame_silver, reference_silver, assessments, source_gold,
    archive, stress_archive,
    stress_record_id_pin=reviewed_stress_record_id,
    expected_recording_fingerprint=reviewed_full_original_recording_fingerprint,
)
```

Seven existing caller-owned handles, preferably read-only, without external/shared
transactions. The last handle is the dedicated stress recording DB and must be
physically separate from all six native inputs, including cursors/attached paths/
hardlink aliases. Source roles retain original supported alias semantics and all
underlying native obligations. Missing memory source paths remain legitimately
unknown/None and are never converted to guessed physical paths. No connections are
opened/closed/initialized by this API. Caller owns their lifetime.

The two explicit reviewed pins refer to the STRESS recording and its FULL original
audit/domain fingerprint, not underlying IV build, native stress/study fingerprint,
stage ID, Git HEAD or ZIP digest. No replacement pins, shocks, terms, IV, spot,
verified/result/study DTO or latest lookup is accepted. No fingerprint refresh occurs.

## Invalidation-first sequence

1. Gate exact native/archive/codec versions and existing byte/numerical profile.
2. Validate both reviewed stress-record pins, then call the ACTUAL original archive
   reader. Known original audit/domain incompleteness returns review before native
   work. Unexpected codec/database exceptions propagate.
3. Require exact typed original recording, requested ID and reviewed full fingerprint.
   Decode/hash-check verified retained bytes. A recorded review_required outcome
   stops BEFORE source/native work and cannot be upgraded by later-good data.
4. Reconstruct the frozen three underlying native pins and exact shock tuple only
   from the verified retained request. Verify physical stress-archive separation.
5. Call the ACTUAL native stress service TWICE with those exact frozen inputs.
   Each call already performs current IV/source revalidation, grid computation,
   another revalidation and repeated grid for positive results. No fake computations,
   volatility refit, tolerance-based match or secondary approximate calculator exists.
6. Validate each COMPLETE returned DTO with the existing strict original record codec,
   including negatives. Re-encode the full canonical envelope with frozen request/
   definition. Compare its COMPLETE bytes against retained record_json and the other
   current envelope. This includes nested native/source evidence and original clocks,
   not merely native/study fingerprints or numerical curves.
7. Reread the actual original recording/audit evidence. Require unchanged COMPLETE
   original DTO and audit fingerprint. Only then expose an accepted current study.

Whole original obligations remain delegated to the actual archive reader; no filters
hide other-scope failed/incomplete/unlinked jobs or orphan events. No native work
runs for unreviewed or recorded-negative originals. Both good-bad and bad-good fresh
outcomes are retained; no later-good selection or old-good cache fallback occurs.
Known original audit failure AFTER the two native passes preserves both observations
and byte comparison in review, but no accepted study/IDs. Unexpected native/kernel/
codec/DB exceptions propagate with NO accepted partial result, retry, write or repair.

## Positive and negative semantics

Positive: matched_current_research_iv_spot_stress_archive. Narrow flags:
- archived_recording_verified
- current_source_checked
- model_computation_rechecked
- exact_recording_reproduced
- archive_unchanged_observed

On a completed fresh-negative pair, current_source_checked records that current-native
checking was invoked/returned, NOT that both source observations were accepted or
that both grids ran. Inspect status and other flags. model_computation_rechecked
requires both native stress calls to complete positively. Full-byte match and stable
original audit evidence are additional independent requirements.

Only positive returns an accepted study, native_stress_fingerprint and
new evidence_fingerprint. Review can retain valid partial facts (e.g. exact bytes
before an after-audit failure), but all accepted output fields remain None. Both full
native DTOs, complete archive before/after DTOs and comparison remain available where
observed. Source option/spot timestamps on positive copy the actual original native
values unchanged, including None. Generic event_ts/published_at remain None.

Unlike the stage digest-only binding, the stress archive DOES retain complete native
stress DTO bytes. Direct full retained/current byte equality is therefore meaningful.
This does not retroactively reconstruct unretained provider originals, authenticate
issuers/receipts, prove past economic/availability validity, or imply complete decision
replay. Byte integrity and repeated observations are not global atomic snapshots,
future validity promises, namespace authority or security against privileged SQL/
whole-file rollback/deletion. Trusted single-owner sources/DBs remain required.

The study itself still says current_source_checked=False because it is a pure
hypothetical numerical DTO. Native/outer source checks concern original input
observations, NOT hypothetical shocked market prices. Price changes remain relative
to the MODEL baseline, not executable premium or portfolio P&L. All volatility-response,
identity, suitability, authenticity, availability, historical, publication, atomicity
and decision-eligibility denials stay false/None. No admission contract is introduced.

## Bounds and write boundaries

Each compared complete envelope <=24 MiB; three compared payloads <=72 MiB, NOT a
process-memory ceiling. Original archive record <=24 MiB, each inner native per-build
observation <=8 MiB, each study <=64 KiB, 1..16 shocks in unchanged -5000..5000.
Two full native stress calls can perform up to 68 stress price/Greek evaluations,
plus their actual underlying IV solver/source work. Canonical/DTO/hash copies add
memory overhead. No nested bounds/tolerances/dependencies/solver settings change.

No audit job, record/contract mutation, initialization, publication, adoption,
recovery, retry, cleanup or new file/CLI is added. Actual read transactions in the
original reader remain; no domain write is performed by this service.

## Tests and honest verification

Sandbox: 20 pure byte-comparison cases plus 1 DTO/signature/default-denial case,
21 passed. These do NOT execute native pricing/revalidation. No model/native
success was fabricated or dependency implementation replicated for testing.
14 repository-native boundary cases are supplied but NOT run here. They use actual
source/model/stress/archive services and the existing lower source substitute unchanged.
They cover complete-byte matching, wrong/unknown reviewed pins, recorded review gate,
changed sources and both negative orderings, original and after-audit failures,
metadata drift, native exceptions, read-only reopening, physical aliases and frozen
underlying archive fingerprint drift. They are not acquisition-native E2E.
Ruff/mypy, mandatory repository QA, Windows runner and full native E2E were NOT run.

Delivery parsing/whitespace and ZIP/CRC/exact-member/checksum verification are separate
from native correctness. See verification report. No existing tests/assertions are
weakened, skips added or original source identity assertion removed.

## Apply and local QA

Verify the ZIP with standalone verifier: ZIP path and --sha256 set to the SEPARATE
64-character whole-archive checksum. Never use a verifier-script manifest hash or
40-character Git HEAD as the ZIP hash. Manifest excludes itself; ZIP checksum covers
all bytes including manifest. Extract into disposable directory, review additions and
copy only if destination does not exist. Reconcile collisions instead of overwriting
accepted fixes. No auto-installer, git staging, commit, push or log deletion occurs.

Run scripts/inspect/qa_research_iv_current_stress_archive.ps1 in the repository.
ExpectedHead must be explicitly reviewed FULL 40-character LOCAL git rev-parse HEAD,
not f52095e, a filename, native/archive evidence fingerprint or ZIP digest. Runner
checks branch/HEAD, actual uv interpreter, ALL five mandatory commands, standalone
verifier lint and additional untracked whitespace. Never auto-fill an unreviewed
HEAD or weaken tests/typing/dependencies/bounds to pass QA.

Real acquisition, user-data loading/migration/backfill, actual identity/key/policy/
authority registrations, production publication, trading and decision-loop cutover
remain on hold. Package QA is not whole-platform acceptance or data-loading permission.
