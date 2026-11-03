# Fixed-IV hypothetical spot-shock research study

## Accepted baseline and source reconciliation

Latest accepted baseline is ed3f6f7, user-reported all QA/tests passed, with local
HEAD and origin/feat/medallion-feature-store aligned. No newer failure/commit was
supplied. Repository access remains unavailable; local Git/QA was not independently
verified. No original source is reconstructed or overwritten by this additive patch.

Inspected actual numerical kernel, canonical bundle/member codec, build record
codec, native price candidate, bundle assembly and current revalidation services.
One important reconciliation: the bundle member retains calculation and terms,
NOT the original spot decimal. The new native service therefore obtains spot from
the actual fresh native Gold evidence, checks unique last_price and exact ratio,
and NEVER reverse-engineers spot from Greeks, invents a price or assumes provider
identities. This package operates on one reviewed native per-build IV result,
not on a staged bundle or recovery-capture result.

## Purpose and model limitation

The existing kernel solves European BSM IV under explicit continuous annual rate,
dividend and assumed expiry terms. This package uses that solved IV as a CONSTANT
while hypothetically changing only spot. It reports model prices, Greeks and model
price CHANGE from the unshocked MODEL baseline. It does not subtract the observed
premium, claim portfolio P&L, apply lot size/positions, assume sticky-strike market
behavior, forecast a volatility smile or authenticate actual instrument suitability.

No provider symbols/tokens/labels are promoted to canonical instrument identities.
Scenario roles are not an authoritative underlying binding. Unknown clocks remain
unknown. Model time/rate/dividend/strike/type stay exactly as supplied in archived
scenario terms. No expiry inference, volatility refit or rescaled Greek units occurs.

## APIs

- research-iv-fixed-vol-spot-stress@1 (numerical study)
- native-research-iv-fixed-vol-spot-stress@1 (actual reviewed native evidence service)

```python
compute_research_iv_spot_stress(
    spot_decimal=exact_spot, terms=explicit_terms,
    fixed_implied_volatility=solved_iv_float,
    shocks_bps=(-1000, -100, 0, 100, 1000),
)

build_native_research_iv_spot_stress(
    bronze, frame_silver, reference_silver, assessments, source_gold, archive,
    build_id_pin=reviewed_iv_archive_build_id,
    expected_archive_fingerprint=reviewed_full_iv_archive_fingerprint,
    expected_revalidation_fingerprint=reviewed_native_iv_revalidation_fingerprint,
    shocks_bps=(-1000, -100, 0, 100, 1000),
)
```

The numerical API is untrusted research input only; current_source_checked=False.
The native API accepts reviewed pins and shock integers, NO caller verified result,
IV/spot/terms replacement DTO, auto-latest lookup or fingerprint refresh. Existing
six handles are caller-owned, preferably read-only, without external transactions.
Original native services retain their archive/source alias checks and audits.
No new DB/CLI/file writer, initialization or publication format is added.

## Exact shocks and bounds

1 basis point is 0.0001 relative spot change. The grid is an immutable sorted unique
tuple of 1..16 exact integers, each -5000..5000 (relative spot factor 0.5..1.5).
Boolean/float/int-like substitutes, duplicates, unsorted grids and empty grids fail.
Zero shock is optional; an unshocked model baseline is always evaluated separately.

Original spot retains the kernel's bounded plain decimal profile: 1e-8..1e9,
<=12 fractional places. The exact derived decimal equals spot*(10000+bps)/10000.
An explicit precision-64 Decimal context avoids ambient-context rounding. Derived
spots have <=16 fractional places, never rounded to fit the original input parser.
They are derived model coordinates, NOT newly received prices or solver inputs.
The existing price_and_greeks API takes float coordinates, as before. The full exact
derived decimal is retained before that normal model float conversion.

Every original/derived spot and exact Decimal spot/strike ratio must remain within
original price/ratio bounds. Kernel bounds remain untouched: spot/strike 1e-8..1e9,
ratio 0.05..20, rates/dividends -0.25..1, assumed years 1e-6..5, IV 1e-6..5, CE/PE
only. Crossing any boundary raises; never clip, expand bounds, skip a cell or return
an accepted prefix. Vega/rho remain per 1.00 absolute unit and theta per 365 model
days. The real solver/brentq settings and all residual/vega gates remain unchanged.
Stress repricing does not itself solve a new IV or impose solver-identifiability
claims on the hypothetical coordinates.

## Native invalidation-first execution

1. Validate profile, exact reviewed pins and bounded grid.
2. Invoke the ACTUAL native per-build revalidator. Require exact reviewed archive
   and full native revalidation fingerprint, complete positive original/current
   evidence and unchanged archive obligations. Review stops BEFORE stress pricing.
3. Reconstruct terms from verified archive bytes, and solved IV from actual fresh
   native calculation. Extract spot from the actual before Gold candidate's unique
   ExactPriceFeature; require numerator/denominator/decimal agreement.
4. Compute baseline and every grid cell through ACTUAL existing BSM kernel calls.
   Require exact baseline BsmValues equality with original solved calculation,
   and actual Python/SciPy runtime equality. No IV-only or rounded comparison.
5. Invoke the ACTUAL native per-build revalidator again. Require complete positive
   result and equality of the COMPLETE canonical before/after observation bytes.
6. Reconstruct and compute the grid AGAIN and require complete result-byte equality.
7. Only then expose accepted study and evidence_fingerprint, with original individual
   source event timestamps copied unchanged (including None).

Positive: computed_current_native_research_iv_spot_stress. Native narrow facts:
current_source_checked, exact_native_observations_matched, stress_results_reproduced.
Here current_source_checked applies ONLY to original source-linked inputs, NOT
hypothetical shocked prices being observed or available market values.

A negative after-read retains before/after native observations and provisional_study
but accepted study/evidence_fingerprint remain None. Unexpected native/kernel/codec/
DB exceptions propagate with no accepted partial return, old-good cache or repair.
A negative initial observation cannot be promoted by later-good state. Provisional
calculations are diagnostics, not accepted output. No retries/writes occur.

The result fingerprint includes exact inputs/terms/shocks, actual runtime versions,
all model values and complete study context. Native fingerprint also binds the
reviewed pins, hashes of both COMPLETE native observations and both full studies.
No original archived-native bytes are relabeled as retained replay; current DTOs are
compared directly. Repeated reads are not a global atomic snapshot or continued
validity guarantee. Trusted single-owner read conditions remain required.

## Resource profile and denials

Numerical result <=64 KiB, <=16 shock cells plus baseline per pass. Complete encoded
per-build native observations each <=8 MiB (same existing assembly-pass size profile);
two compared encodings <=16 MiB. These are payload bounds, NOT a process-memory
ceiling. A full pair of numerical passes performs at most 34 price/Greek evaluations,
in addition to existing actual native revalidation's solver/source work. No original
inner source/archive/kernel bounds or numerical tolerances change.

All identity, suitability, authenticated acquisition, availability, historical
validity, publication, atomicity, portfolio-P&L and eligibility denials stay false;
generic canonical_contract_id/event_ts/published_at remain None. No actual namespace
or governance approval, trust root or real data registration is introduced.

## Verification and local QA

Executed in sandbox: 33 input/Decimal arithmetic tests. This is NOT model numerical
verification or native integration. The retrieved kernel is not an importable
repository checkout here; it was NOT reconstructed or replaced with a fabricated
model/dependency harness to claim successful pricing tests.
13 real-model numerical cases and 7 actual-native boundary cases are supplied but
NOT run here. They use actual model/SciPy/brentq and existing native fixture APIs,
with the lower source substitute unchanged. They are not acquisition-native E2E.
No successful native computations were mocked. Ruff/mypy and mandatory repository
QA were NOT run. Syntax/whitespace/archive/checksum checks are separate evidence.

Verify the ZIP via standalone verifier (ZIP path + --sha256 with separate 64-character
archive hash). Manifest excludes itself; separate ZIP checksum includes manifest.
Extract into a disposable folder. Inspect additions; copy only where destinations
do not exist and reconcile collisions instead of overwriting committed fixes.
Run scripts/inspect/qa_research_iv_spot_stress.ps1 from the repository. ExpectedHead
requires explicitly reviewed FULL 40-character LOCAL git rev-parse HEAD, not ed3f6f7,
a filename, archive/native fingerprint or ZIP digest. Runner reports actual uv Python
and runs all five mandatory QA commands without staging/discarding unrelated files.
Passing this package is not full-platform acceptance or lifting the data-loading hold.

No live acquisition, user loading/migration/backfill, real identity/key/policy/
authority registration, production publication, trading or cutover is executed.
