# Baseline delta/gamma attribution of fixed-IV research spot stress

## Accepted baseline and inspected sources

581c319 is the accepted user-reported QA-passed HEAD/origin baseline. dfd3fae is the
accepted current stress-archive revalidator milestone. No newer failure or commit
was supplied. Actual current numerical/native stress sources, record codec, current
archive revalidator, current inspection CLI and fixture interfaces were retrieved,
including their latest formatting. No existing source, committed fix, assertion,
model bound, solver tolerance, dependency or fixture helper is replaced.
Repository access is unavailable; local branch/full HEAD/QA are not independently
reproduced. Historical delivery statements about sandbox tests do not revoke the
user's accepted local QA reports.

## What is newly calculated

For each existing hypothetical spot-shock coordinate, let dS be shocked spot minus
original spot, and delta/gamma be the ORIGINAL unshocked BSM baseline Greeks.

- delta_component = delta * float(dS)
- gamma_component = (0.5 * gamma) * (float(dS) * float(dS))
- delta_gamma_approximation = delta_component + gamma_component
- delta_only_residual = full_model_price_change - delta_component
- second_order_residual = full_model_price_change - delta_gamma_approximation
- reconstruction_roundoff = (delta_gamma_approximation + second_order_residual)
  - full_model_price_change

The evaluation order above is part of @1. Full model change is retained from the
actual existing full BSM repricing study, not replaced by a Taylor estimate. Delta
and gamma use original absolute spot units, NOT percentage changes or changed Greeks
at the shocked point. Strike, IV, rates/dividend and assumed time stay fixed exactly
as in the original stress scenario. No time/theta, rho, vega, smile or position term
is added. This is one-coordinate model sensitivity attribution, not portfolio P&L.

Taylor residual can be large and can have either sign. It includes neglected
higher-order behavior, coordinate float conversion and floating-point price/arithmetic
effects; it is NOT a rigorous truncation error bound. Reconstruction roundoff is
separately exposed, not forced to zero. No tolerance is used to certify approximate
accuracy, clip terms or reject a large but finite residual. Equality of repeated
results proves neither approximation quality nor strategy suitability.

## Exact coordinate and numerical profile

Original spot strings: existing bounded plain decimal, <=12 fractional places.
Shocked coordinates: <=16 fractional places. Both 1e-8..1e9 and relative factor
0.5..1.5. Exact subtraction occurs in an explicit Decimal Context: precision64,
ROUND_HALF_EVEN, Emin=-999999, Emax=999999, clamp0. This isolates precision,
rounding/sign-of-zero and exponent behavior from the caller's ambient context.
The exact decimal change AND its model-arithmetic float conversion are retained.
No original price string is rounded, normalized, clamped or inferred from Greeks.
Nonfinite/wrong-type coefficients, negative gamma, invalid coordinates or nonfinite
intermediate arithmetic raise rather than returning a prefix. A pure arbitrary
coefficient input is NOT a claim that those coefficients came from BSM or a source.

## APIs

- research-iv-spot-stress-delta-gamma-attribution@1
- native-research-iv-stress-delta-gamma-attribution@1

```python
decompose_spot_move(
    base_spot_decimal="100.00", shocked_spot_decimal="101.00",
    baseline_delta=0.5, baseline_gamma=0.02, full_model_price_change=0.75,
)

attribute_research_iv_spot_stress(study)

build_native_research_iv_stress_attribution(
    bronze, frame_silver, reference_silver, assessments,
    source_gold, archive, stress_archive,
    stress_record_id_pin=reviewed_stress_record_id,
    expected_recording_fingerprint=reviewed_full_recording_fingerprint,
)
```

The scalar example is explicit arithmetic input, NOT an observed or computed BSM
price. The pure study transform requires the actual typed @1 study and immutable
points, existing exact shock profile and byte bound. It uses the actual @1 record
codec's _study helper (version/bound gated), rather than copying its schema or
inventing another pricing kernel. Structural/self-hash validation does not establish
provenance/math truth. Its current_source_checked remains False. Source study SHA,
study evidence fingerprint and source runtime labels are retained, alongside the
ACTUAL attribution Python version, explicit Decimal profile and evaluation method.
No source SciPy pricing is performed by the scalar decomposition itself.

Native API accepts only seven caller-owned existing DB handles and two reviewed
stress-record pins. NO caller study, baseline coefficients, grid, terms, IV, spot or
replacement source pins/result DTO is accepted. Prefer read-only handles without
external/shared transactions. All actual archive/Gold/identity alias/audit obligations
remain with the existing accepted current revalidator; no new connections or writes.

## Native invalidation-first execution

1. Validate exact version/bound profile and reviewed stress record ID/fingerprint.
2. Invoke the ACTUAL current stress-archive revalidator. It checks original audit,
   reconstructs frozen pins/grid, runs TWO actual native stress observations and
   compares complete retained bytes with actual current results.
3. Require full typed positive context, all five narrow facts, complete observations,
   accepted study and valid evidence IDs/denials. A negative or recorded-review result
   stops BEFORE attribution; no later-good selection.
4. Calculate new baseline delta/gamma components/residuals over the actual study.
5. Invoke the ACTUAL complete current revalidator AGAIN. Require full positive and
   COMPLETE canonical context-byte equality with the first observation, not just
   equal study, price, IV or evidence-hash field.
6. Compute the attribution AGAIN and compare complete result bytes exactly.
7. Only then expose accepted attribution/evidence and original individual source
   clocks copied unchanged, including None. Generic event_ts/published_at stay None.

Positive: computed_current_native_research_iv_stress_attribution. Narrow facts:
current_source_checked, model_computation_rechecked, current_context_matched,
attribution_reproduced. These concern original source/model evidence and repeated
arithmetic, not validity of hypothetical shocked prices or certified Taylor accuracy.
After a failed second context, provisional_attribution may remain as diagnostic,
but accepted attribution/evidence_fingerprint stay None. Both context observations
remain available. Unexpected native/codec/model/DB/arithmetic exceptions propagate
with NO accepted partial return, cached old-good result, repair or fingerprint refresh.

approximation_accuracy_certified is ALWAYS False, even at zero shock or repeated
identical arithmetic. Portfolio P&L, volatility-response behavior, canonical identity,
model suitability, acquisition authenticity, availability, historical validity,
publication, atomicity and decision eligibility remain false/None. No new trust root,
actual governance approval, model admission, production publication or trade is added.

## Resource and evidence limitations

Study/attribution payloads each <=64 KiB, 1..16 points, original +/-5000bps shock bound.
Each encoded COMPLETE current archive-revalidation context <=160 MiB, a deliberate
outer DTO cap accommodating two <=24 MiB retained record strings (escaped in outer
JSON), two fresh native stress DTOs and metadata. Two compared contexts <=320 MiB,
NOT a process-memory ceiling. DTO/canonical/hash copies add overhead. Existing nested
24 MiB archive, 8 MiB per-build and 64 KiB study bounds remain unchanged.

Two actual current-context calls imply four native stress calls, up to 136 existing
stress price/Greek evaluations plus underlying actual IV solver/source work. New
attribution performs only bounded elementary arithmetic, twice. No kernel constants,
brackets, residual/vega gates or numerical tolerances change. No aggregate positions,
lot size, cross-instrument netting, VaR, empirical model risk or accuracy bound is
inferred. Source-study hashes are links, not retained-original provider replay.
Repeated observations are not global atomic snapshots, future-validity promises or
protection against hostile/privileged rewriting or whole-file rollback/deletion.

## Verification

Sandbox executes the actual new scalar attribution arithmetic: 33 cases covering
known coefficients, signs, zero, exact small decimals, explicit contexts, residuals,
visible reconstruction roundoff, bounds/types and nonfinite intermediates. These are
NOT native/model source computations; no successful native computations or dependency
implementations were mocked/replicated. Four real-model study-transform cases and
seven actual-native boundary cases are supplied but NOT executed here. They use
actual kernel/codec/current archive services and the unchanged lower source fixture
substitute. They are not acquisition-native E2E. No assertion was removed, test skipped,
source price fabricated or dependency downgraded to make checks pass.

Ruff/mypy, ALL mandatory repository QA, Windows PowerShell runner and full native E2E
are NOT run. Source modules were retrieved as project snapshots, not an executable
local checkout. Parsing/whitespace/archive/checksum checks are separate from native
correctness. See delivered verification report for exact execution/integrity results.

## Apply and local QA

Verify ZIP with standalone verifier: ZIP path and --sha256 set to the SEPARATE
64-character archive digest, NOT a verifier-script manifest hash or Git HEAD.
Manifest excludes itself; whole-ZIP checksum includes manifest. Extract to disposable
folder, inspect additions and copy only where destinations do not exist. Reconcile
collisions instead of overwriting accepted source fixes. No auto-installer/staging/
commit/push, production data action or unrelated-log deletion is performed.

Run scripts/inspect/qa_research_iv_stress_attribution.ps1 from repository root with
ExpectedHead = explicitly reviewed FULL 40-character LOCAL git rev-parse HEAD.
It is NOT 581c319, a filename, native/study/archive fingerprint or ZIP checksum.
Runner checks branch/HEAD, uv-selected interpreter, ALL five mandatory QA commands,
standalone verifier lint and additional untracked whitespace. Never auto-fill an
unreviewed HEAD or weaken tests/typing/bounds/dependencies to pass QA.

Acquisition/user-data loading/migration/backfill, real identity/key/policy/authority
registrations, production publication, trading and cutover remain on hold. Package
QA is not whole-platform acceptance or permission to load user data.
