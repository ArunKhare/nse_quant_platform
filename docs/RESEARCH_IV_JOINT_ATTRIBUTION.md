# Baseline delta/gamma/vega attribution of hypothetical spot/vol surfaces

## Baseline and actual source reconciliation

7610930 is the accepted user-reported QA-passed HEAD/origin baseline; a400908 is the
accepted hypothetical spot/vol surface milestone. No newer failure/commit was supplied.
Actual surface/model, one-dimensional attribution and native/current archive interfaces
were retrieved. The latest surface CLI did not return within the bounded retrieval
attempts; it is NOT a dependency and is NOT reconstructed or modified. Necessary
numerical/native interfaces were available. No accepted source, formatter fix, test,
assertion, context, dependency, solver setting or tolerance is overwritten/changed.
Repository access remains unavailable, and local HEAD/QA are not independently
reproduced. Historical sandbox limitations do not revoke accepted user QA reports.

## New joint approximation, not full second-order Hessian

For each full-repriced surface cell:
- Reuse ACTUAL accepted decompose_spot_move for baseline delta*dS and half-gamma*dS^2.
  Its reference full spot-only change remains the original fixed-IV spot repricing.
- Compute an additional baseline vega_per_vol_unit*dSigma_effective.
- delta_gamma_vega_approximation = spot_delta_gamma_approximation + vega_component.
- joint_residual = full_joint_model_price_change - delta_gamma_vega_approximation.
- reconstruction_roundoff = (approximation + joint_residual) - full_joint_change.

The evaluation order above is fixed in @1. Full joint model changes remain those
from ACTUAL existing BSM surface repricing, never replaced by an approximate price.
The result retains the complete old spot decomposition and a separate VegaResidual.
No vanna, volga, theta/time, rho/rate, changing-Greek or position/lot-size terms are
computed. vanna_volga_included=False explicitly: this is NOT a full second-order
spot/vol Hessian approximation. Residual includes omitted cross/vol curvature,
higher-order spot behavior, coordinate/float and pricing effects, NOT a certified
error bound or unique causal/empirical P&L attribution. Large residuals remain visible.
No residual threshold, correction-to-zero, clipping or approximation acceptance
threshold is used. Even exact zero residual does not certify Taylor accuracy.

## Critical units and nominal/effective sigma distinction

Existing kernel vega is per 1.00 ABSOLUTE annual sigma, NOT per percentage point.
The existing surface accepts nominal additive volatility basis points: 1bp=0.0001
sigma; +100bps=+0.01 sigma. The nominal decimal offset is retained per cell.

Surface coordinates start from the exact binary solved float plus that nominal
Decimal offset and are converted to float for actual BSM pricing. This package uses
EFFECTIVE model-coordinate change for the vega term:
Decimal.from_float(shifted_model_sigma) - Decimal.from_float(base_model_sigma).
That exact difference is computed with precision128, ROUND_HALF_EVEN, Emin=-999999,
Emax999999, clamp0, then converted to float for multiplication. Both original sigma
hex values, exact effective decimal and effective float delta are retained.

For example an exact nominal +0.01 offset need not equal the exact difference of
the two converted model floats. Neither is rounded into the other. Spot attribution
intentionally keeps the accepted 1D method: exact original Decimal dS converted to
float. Joint residual therefore includes that method's spot-coordinate float effects.
No implicit vega scaling by 100/10000 or relative-percent-vol interpretation occurs.
Original kernel float bracket [1e-6,5], including its binary lower endpoint, stays
unchanged. Nonfinite/wrong-type sigmas/scalars, negative vega or nonfinite intermediate
arithmetic raise without accepted partial result. No hypothetical column is dropped.

## APIs and pure evidence limitations

- research-iv-spot-vol-delta-gamma-vega-attribution@1
- native-research-iv-spot-vol-joint-attribution@1

```python
decompose_vega_residual(
    base_volatility=0.25, shifted_volatility=0.5,
    baseline_vega_per_vol_unit=40.0,
    spot_taylor_price_change=2.0, full_model_price_change=12.5,
)

attribute_research_iv_spot_vol_surface(surface)

build_native_research_iv_joint_attribution(
    bronze, frame_silver, reference_silver, assessments,
    source_gold, archive, stress_archive,
    stress_record_id_pin=reviewed_stress_record_id,
    expected_recording_fingerprint=reviewed_full_recording_fingerprint,
    vol_shifts_bps=(-100, 0, 100),
)
```

Scalar example is explicit arithmetic input, NOT BSM/provider/native truth. Pure
surface transform requires the actual typed @1 full surface with supported profile,
research denials, immutable complete Cartesian grid, source self-hash, exact supported
vol coordinates and source runtime labels. Actual one-dimensional attribution helper
is reused unchanged; no cloned BSM/dependency or copied old delta/gamma arithmetic.
Self-consistency does not prove provenance or model truth: pure current_source_checked
remains False. Source surface fingerprint/SHA and actual source/attribution runtimes
bind exact input/method/coordinates/values; no rounding removes runtime differences.

## Native evidence-bound execution

Seven existing caller-owned handles, preferably read-only without external/shared
transactions. Caller supplies exact reviewed STRESS recording ID/full original
recording fingerprint and ONLY the new hypothetical vol-shift tuple. NO baseline
coefficients, spot grid, IV/terms, surface/study/native DTO, replacement source pins,
latest lookup or automatic fingerprint refresh is accepted. Original native archive/
source identity/alias/audit obligations stay with the actual current revalidator.

1. Gate exact versions/bounds; validate reviewed pins and new vol-grid shape BEFORE
   native work. Frozen original spot rows/base IV remain owned by the original record.
2. Invoke ACTUAL current stress-archive revalidation, requiring full positive context,
   all five narrow facts, evidence IDs, complete observations and research denials.
   A recorded review/negative stops BEFORE any surface/attribution computation.
3. Build the ACTUAL full spot/vol surface from that returned study via the accepted
   numerical surface API, then compute new joint attribution from actual baseline
   Greeks and full cell changes. No copied success DTO or alternate pricing engine.
4. Invoke ACTUAL full current archive revalidation AGAIN. Require full positive and
   COMPLETE canonical context-byte equality, not merely matching prices/study IDs.
5. Reprice the whole surface AGAIN, compare complete surface bytes, then recompute
   attribution AGAIN and compare complete attribution bytes.
6. Only then expose accepted surface/attribution/evidence and unchanged original
   individual source clocks, including None; generic event_ts/published_at stay None.

Native service deliberately orchestrates the public numerical surface API directly
inside its own evidence bracket, avoiding nested calls to the already bracketed native
surface wrapper and unnecessary duplication of huge parent contexts. All source/model
work remains actual; no source protocol is bypassed or relabeled as current.

Positive: computed_current_native_research_iv_joint_attribution. Narrow facts:
current_source_checked, model_computation_rechecked, current_context_matched,
surface_reproduced, attribution_reproduced. These describe original input checks and
repeated computations, NOT observed market responses or certified approximation.
If later source/audit context or numerical output drifts, diagnostics may retain
provisional surfaces/attributions and both observed contexts, but accepted surface/
attribution/evidence_fingerprint remain None. Unexpected native/codec/model/DB/math
exceptions propagate without accepted partial return, cache fallback, later-good
selection, retry, repair or fingerprint refresh.

## Bounds and denials

Original grid <=16 spot rows x <=8 vol columns = <=128 cells. Source surface and
joint attribution each <=256 KiB. Existing vol shifts remain sorted unique exact ints
in -5000..5000. Each encoded COMPLETE current context <=160 MiB; two compared contexts
<=320 MiB, NOT a process-memory ceiling. DTO/canonical/hash copies add overhead.
Original 24 MiB records, 8 MiB per-build and 64 KiB spot-study bounds remain untouched.
No maximum is enlarged to make a point, column, cell, float or test pass.

Two actual current-context calls entail four original native stress calls (up to136
original stress evaluations plus actual underlying IV solver/source work). Two new
surfaces add up to306 existing kernel evaluations, with bounded elementary joint
arithmetic over <=128 cells per pass. No solver/root refit, vanna/volga engine or
new external dependency is added. Pure arithmetic does not itself call SciPy.

approximation_accuracy_certified=False and vanna_volga_included=False ALWAYS.
hypothetical_volatility_shift_assumed=True explicitly; endogenous volatility response,
portfolio P&L, canonical identity/binding, terms authority, model suitability,
acquisition authenticity, availability, historical validity, publication, atomicity
and eligibility remain False/None. No trust root, real authority/key registration,
strategy admission, publication, staging or trading contract is introduced. Repeated
observations/self-hashes do not prove economic-time validity, issuer authenticity,
global atomic snapshots, future validity or privileged/whole-file rollback security.

## Honest verification and application

Sandbox executes 39 actual new scalar/Decimal/vega arithmetic cases, including vega
units, signed changes, nominal/effective float distinction, explicit contexts,
nonfinite rejection, original binary lower endpoint, large residuals and visible
roundoff. This is NOT BSM or native integration. Four actual-model surface-transform
cases and seven native boundary cases are supplied but NOT executed here. They use
actual accepted model/surface/spot-attribution/archive APIs and unchanged lower source
substitution. No successful-native computation or dependency implementation is
fabricated/replicated. No skips, weaker assertions, type ignores, tolerance changes
or dependency downgrades are added. These cases are not acquisition-native E2E.
Ruff/mypy, ALL mandatory repository QA, Windows runner and full native E2E are NOT
run. Parsing/whitespace/archive/CRC/member/checksum checks are separate evidence.

Verify ZIP using standalone verifier with ZIP path and --sha256 equal to SEPARATE
64-character archive checksum, NOT a verifier-script manifest hash or Git HEAD.
Manifest excludes itself; whole ZIP checksum includes manifest. Extract to disposable
folder, inspect additions and copy only where destination does not exist. Reconcile
collisions instead of overwriting accepted fixes. No auto-install/staging/commit/
push, production actions or unrelated-log deletion occurs.

Run scripts/inspect/qa_research_iv_joint_attribution.ps1 with ExpectedHead equal to
explicitly reviewed FULL 40-character LOCAL git rev-parse HEAD, NOT 7610930, a filename,
evidence fingerprint or ZIP digest. Runner checks branch/HEAD, actual uv interpreter,
ALL five mandatory commands, standalone verifier lint and additional whitespace.
Do not auto-fill an unreviewed HEAD or weaken checks to pass QA. Package QA is not
whole-platform acceptance or permission to lift the data-loading hold.

Real acquisition/loading/migration/backfill, identity/key/policy/authority registrations,
production publication, trading and cutover remain prohibited.
