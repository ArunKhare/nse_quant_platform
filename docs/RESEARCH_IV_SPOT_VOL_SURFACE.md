# Bounded hypothetical spot x additive-volatility research surface

## Baseline and source reconciliation

52b1375 is the latest accepted user-reported QA-passed HEAD/origin baseline; 859bd27
is the accepted native attribution milestone. No newer failure/commit was supplied.
Actual current BSM kernel, stress/numerical/attribution/CLI sources, record codec,
current archive revalidator, native fixtures and pyproject were retrieved. This
additive package does not overwrite accepted formatting fixes or change the kernel,
solver settings, original profiles, source assertions, dependencies or fixtures.
Repository access is unavailable; local full HEAD/branch/QA were not independently
reproduced. Historical unexecuted-sandbox wording does not revoke user acceptance.

## Substantive new calculation

The original study varies spot at constant solved IV. This package evaluates a bounded
Cartesian product of that SAME spot grid and an explicit new hypothetical volatility
axis through the ACTUAL existing BSM price_and_greeks. It does not infer a market
smile, endogenous volatility response, positions, lot size, P&L or strategy eligibility.

For each cell (S_shock, sigma_shift), with original model baseline V0:
- full_model_price_change = V(S_shock, sigma_shift) - V0
- spot_only_change = original V(S_shock, sigma0) - V0
- vol_only_change = V(S0, sigma_shift) - V0
- interaction_change = (full_model_price_change - spot_only_change) - vol_only_change
- reconstruction_roundoff = ((spot_only_change + vol_only_change) + interaction_change)
  - full_model_price_change

This is a finite-difference separation of hypothetical model changes, not Taylor
attribution, an exact real-arithmetic identity, a response forecast or empirical risk
estimate. Interaction can have either sign. Roundoff remains visible, not zeroed.
No residual/interaction threshold certifies accuracy or chooses successful output.
Every cell retains full unrounded BsmValues with original Greek units (vega/rho per
1.00 absolute unit; theta /365 model days). All terms except spot/assumed sigma stay
unchanged, including original explicitly assumed years, rate, dividend, strike/type.
Unknown provenance/availability/economic clocks and canonical identities stay unknown.

## Exact volatility axis semantics

1 volatility basis point means 0.0001 ABSOLUTE annual sigma, NOT 0.01% of sigma0.
Thus +100bps means +0.01 absolute sigma (one volatility percentage point), independent
of base IV. Caller grid is an immutable sorted unique tuple of 1..8 exact ints within
-5000..5000. No float/bool, dedup/sort, implicit zero column or bracket expansion.
The frozen original spot grid remains 1..16 rows; <=128 total cells, row-major order.
Original unshocked baseline is always evaluated even when no zero row/column is asked.

Base IV is an actual solved float, NOT an authoritative exact decimal. Coordinate
construction uses Decimal.from_float(base_iv) + Decimal(shift_bps)/10000 under explicit
precision128, ROUND_HALF_EVEN, Emin=-999999, Emax999999, clamp0. The supported float
bracket's exact decimal expansions fit this precision. The exact derived decimal,
converted float and float.hex are retained. Zero offset preserves original float
bits. No shortest-decimal representation or quantization replaces the base IV.

Important boundary reconciliation: float(1e-6) is not exactly Decimal('0.000001').
Exact-coordinate bounds use Decimal.from_float of the ACTUAL kernel float endpoints,
not a stricter/different decimal literal. Zero at the supported binary lower endpoint
therefore stays valid. Both exact derived coordinate and converted float must remain
inside the original [1e-6,5] float bracket. If any column is outside, the ENTIRE surface
raises; no column/cell is dropped, clipped or made-up. IV is never solved again at a
hypothetical cell. Original actual brentq/residual/vega gates remain untouched.

## APIs

- research-iv-hypothetical-spot-vol-surface@1
- native-research-iv-hypothetical-spot-vol-surface@1

```python
shifted_volatility(base_volatility=0.2, shift_bps=100)
compute_research_iv_spot_vol_surface(study, vol_shifts_bps=(-100, 0, 100))

build_native_research_iv_spot_vol_surface(
    bronze, frame_silver, reference_silver, assessments,
    source_gold, archive, stress_archive,
    stress_record_id_pin=reviewed_stress_record_id,
    expected_recording_fingerprint=reviewed_full_original_recording_fingerprint,
    vol_shifts_bps=(-100, 0, 100),
)
```

Pure surface accepts the actual typed original spot-stress study; it validates the
original immutable row grid, full canonical study/hash profile via the ACTUAL @1
record codec's _study helper (version/bound gated), and actual current runtime equality.
It rechecks baseline and every original fixed-IV spot-axis value through the actual
kernel with exact equality. Zero-vol cells must reproduce original full BsmValues.
Structural/self-hash consistency or offline repricing is NOT native source evidence;
pure current_source_checked remains False.

The native API accepts seven existing caller-owned handles and two reviewed STRESS
record pins plus ONLY the new assumed volatility-shift grid. It accepts NO replacement
spot grid/base IV/terms/source pins/result DTO, latest lookup or fingerprint refresh.
The reviewed pins are stress recording ID and FULL original audit/domain fingerprint,
not an IV build/study/native/attribution ID, Git HEAD or ZIP digest. Prefer read-only
handles without external/shared transactions. Original physical alias, full archive/
audit and source/Gold obligations remain delegated to the actual current revalidator.

## Native invalidation-first execution

1. Gate exact dependency/profile versions and validate reviewed pins/new integer grid.
2. Invoke the ACTUAL current stress-archive revalidator, which checks original audit,
   reconstructs frozen inputs, performs two real native stress observations and
   compares complete retained bytes. Require full typed positive context and denials.
   Recorded-review/initial-negative contexts stop BEFORE any new surface pricing.
3. Obtain the original study ONLY from this actual returned accepted context. Reprice
   new surface with actual BSM. Validate all derived vol coordinates before any new
   baseline/axis/cell repricing; out-of-profile assumptions raise without partial output.
4. Invoke the ACTUAL complete current archive revalidator AGAIN, requiring full positive
   and COMPLETE canonical context-byte equality, not merely matching prices or IDs.
5. Recompute the whole surface AGAIN and require complete result-byte equality.
6. Only then expose accepted surface/evidence and original individual source timestamps
   copied unchanged, including None. Generic event_ts/published_at remain None.

Positive: computed_current_native_research_iv_spot_vol_surface. Narrow facts:
current_source_checked, model_computation_rechecked, current_context_matched,
surface_reproduced. These concern original source/model checks and repeated numerical
work, not observed market prices at shocked coordinates. hypothetical_volatility_shift_assumed
is explicitly True. volatility_response_modelled, portfolio_pnl_asserted, underlying
identity, terms authority, suitability, acquisition authenticity, availability,
historical validity, publication, atomicity and eligibility stay False/None.

If later context becomes negative/drifts, both observations and provisional_surface
remain diagnostic but accepted surface/evidence_fingerprint stay None. No later-good
selection or old-good cache fallback. Unexpected source/codec/model/DB/arithmetic
exceptions propagate without accepted partial return, repair or fingerprint refresh.
A completed valid numerical hypothetical surface is not market suitability or authority.

## Bounds and evidence limitations

<=8 columns x <=16 original rows = <=128 cells. Complete surface <=256 KiB. Each pure
compute performs at most 153 existing kernel calls: baseline1 + source-axis16 +
base-spot column8 + cell128. Native repeat means at most306 new surface kernel calls,
plus up to136 original stress evaluations and underlying IV solver/source work from
two actual current-context calls. Runtime differences and float details are retained
exactly in fingerprints, not rounded away.

Each COMPLETE encoded native current context <=160 MiB; two compared contexts <=320
MiB, NOT a process-memory ceiling. DTO/canonical/hash copies add memory overhead.
Original 24 MiB record, 8 MiB per-build, 64 KiB study and all kernel domains remain
unchanged. Original exact spot constraints/ratios still apply; no bounds expand to
make a cell pass. Full native before/after contexts are retained when observed.
Repeated observations are not global atomic snapshots, future-validity guarantees,
issuer authentication or privileged/whole-file rollback protection.

No new DB/file/CLI writer, persistence contract, model solver, provider acquisition,
identity assertion, publication/admission path, portfolio/strategy/trading logic or
recovery authority is added. Existing accepted CLI/attribution APIs remain untouched.

## Verification and application

Sandbox executes 39 actual new input/vol-coordinate arithmetic tests, including exact
binary-root offsets, original lower endpoint, explicit Decimal context, zero-bit
preservation and no clamping. This is NOT actual BSM repricing or native integration.
Five real-model surface cases (call/put, each cell/zero axes, scenario columns,
out-of-domain whole-set rejection and output cap) and seven actual-native boundary
cases are supplied but NOT executed here. Native tests use actual current/archive/
model services with existing lower source substitution unchanged. No successful
native computations or dependency implementations are fabricated/replicated.
No source identity assertion is changed, skip added or dependency/tolerance weakened.
Ruff/mypy, actual mandatory repository QA, Windows runner and full native E2E are
NOT run. See verification report for precise counts and separate archive integrity.

Verify ZIP using standalone verifier: ZIP path plus --sha256 with the SEPARATE
64-character archive checksum, NOT a verifier-script hash from MANIFEST or Git HEAD.
Manifest excludes itself; whole-ZIP checksum includes manifest. Extract into disposable
folder, review additions and copy only where destinations do not exist. Reconcile
collisions rather than overwrite accepted fixes. No auto-install/staging/commit/push,
production actions or unrelated-log deletion is performed.

Run scripts/inspect/qa_research_iv_spot_vol_surface.ps1 with ExpectedHead equal to the
explicitly reviewed FULL 40-character LOCAL git rev-parse HEAD, not 52b1375, a filename,
evidence fingerprint or ZIP hash. Runner checks branch/HEAD, actual uv interpreter,
ALL five mandatory commands, standalone verifier lint and additional whitespace.
Do not auto-fill an unreviewed HEAD or weaken checks to pass QA. Package QA is not
whole-platform acceptance or permission to lift the acquisition/data-loading hold.

Real acquisition/loading/migration/backfill, identity/key/policy/authority registrations,
production publication, trading and decision-loop cutover remain prohibited.
