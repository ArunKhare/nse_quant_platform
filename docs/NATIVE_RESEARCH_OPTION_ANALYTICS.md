# Native research European BSM IV/Greeks candidate @1

## Reconciliation / why this package

Latest USER-REPORTED HEAD9442898 on feat/medallion-feature-store and origin,
accompanied by QA/Test update. No independent local HEAD/branch verification,
repository writes, staging, commit or push by assistant. Inspected actual uploaded
GoldQuoteCandidate/ExactPriceFeature, gold_quote_reader, feature_bundle, legacy
analytics/option_analytics.py, actual Gold reader tests and pyproject.toml.
Gold exact-provider-price inputs currently have no native IV/Greeks model in the
returned sources. This new capability addresses required analytics rather than
adding another conditional-authority wrapper with no genuine trust root supplied.
The independent authority gate is NOT closed or bypassed.

Existing source unchanged; copy ABSENT additions only. Stop/compare if a target
exists. Python >=3.12/scipy>=1.14.0 from ACTUAL pyproject remain unchanged. No extra
dependency, native dependency replica or alternate legacy adapter is added.

## Actual computation / numerical contract

research-european-bsm-iv@1 is European Black-Scholes-Merton with continuous annual
risk-free rate and continuous dividend yield, spot and strike in caller-assumed
comparable quote units. European exercise/model suitability is an EXPLICIT research
assumption, not inferred from provider token, trading symbol or identity evidence.

    ScenarioTerms(strike, annual_rate, annual_dividend_yield,
                  assumed_years_to_expiry, option_type)
    scenario_terms_sha256(terms)
    compute_research_iv(spot_decimal=..., premium_decimal=..., terms=...)
    price_and_greeks(spot, strike, years, rate, dividend, volatility, option_type)

Inputs preserve original decimal strings: bounded plain decimal syntax, no scientific
notation/NaN/infinity/coercion. Prices converted explicitly to binary64 for analytics;
source prices are never overwritten or presented as approximate provider originals.

Fixed profile bounds:
- spot/strike/premium 1e-8..1e9; spot/strike ratio 0.05..20
- annual rates/dividend yield -0.25..1.0
- assumed year fraction 1e-6..5; CE or PE ONLY, no fallback option-type branch
- IV bracket 1e-6..5.0; not expanded/clamped to get a solution
- strict discounted European lower/upper premium bounds
- actual scipy.optimize.brentq: xtol=1e-12, rtol=1e-12, maxiter=256
- require convergence, abs residual <=1e-8+1e-10*max(premium,1), positive local vega>1e-8
- reject unidentifiable bracket/unsupported premium with review_required, no invented IV

Price OTM side first and use put-call parity for ITM side. Normal CDF from actual
scipy.special.ndtr; no native statistical dependency replica. Greeks: delta, gamma,
vega_per_vol_unit, theta_per_calendar_day, rho_per_rate_unit. Vega/rho per 1.00
absolute vol/rate change; divide by100 for per-percentage-point display. Theta uses
365 model days/year. Output price and all Greeks must be finite, price nonnegative.
No lots/multiplier/currency label inferred. Inputs with invalid supported-domain
shape raise fixed ValueError rather than being coerced or silently clamped.

Input fingerprint binds exact decimal strings, scenario terms, all numerical bounds,
solver tolerances/limits, actual SciPy version AND Python runtime version. Calculation
ID binds complete result with ID empty. This records numerical context; it is not
cross-platform bitwise reproducibility or full platform exact replay. No rounding
pretends to establish native source authenticity.

## Native Gold-consuming builder

    build_native_research_iv_candidate(
        bronze, frame_silver, reference_silver, assessments, gold,
        option_build_id=..., spot_build_id=..., terms=...,
        expected_scenario_terms_sha256=...,
    )

Two DISTINCT exact reviewed Gold build pins plus exact scenario-terms fingerprint.
Actual read_quote_price_build is called for option and spot roles, calculation is
performed, then BOTH source roles are re-read. Complete current native results and
full before/after DTO equality required. Superseded/blocked source or observed drift
returns review_required, no earlier-good fallback. Any retained calculation inside
a review result is diagnostic only, NEVER admissible as a successful feature.
Native SQL/source failures propagate rather than becoming numeric/market success.

Select only unique last_price; verify original numerator/denominator/decimal agreement
using actual exact_price_decimal. Zero remains a real observed zero in source DTO;
new analytics refuses it rather than replacing it with a made-up premium. Original
option/spot event_ts are copied, including None. Receipt/now/expiry defaults are NEVER
substituted for unknown source clocks. Native builder performs no writes or I/O opens.
Owned existing source/Gold connections; no outer transactions. Source checks inherit
the exact EXISTING Gold reader profile, not stronger audit/authentication claims.

Caller assigning a Gold build to spot/option roles does not prove contract/underlying
identity or equal economic time/currency. option_underlying_identity_binding_verified
and scenario_terms_authoritative remain FALSE. canonical_contract_id stays None.
assumed_years_to_expiry is a caller SCENARIO fraction, not recovered/verified original
expiration or economic validity. No observed economic clock is backfilled from it.

Positive status research_iv_candidate means in-memory research calculation with
native price inputs rechecked. It is NOT persisted/audited Gold analytics, feature
publication, eligible bundle/admission, authenticated provenance, validated identity,
model suitability, historical-validity/availability claim or decision-loop cutover.
No availability/identity/publication/decision flags promoted. No IV rank/history or
production exit threshold changes. Legacy enrich_quote and its365.25 conventions,
legacy option_stream and historical IV/Greeks remain untouched.

## Validation honesty

37 focused numerical tests passed with REAL installed SciPy1.13.1/Python3.12.8 in
sandbox. IMPORTANT: SciPy1.13.1 is BELOW project's declared >=1.14.0 minimum.
This is NOT supported-project dependency QA. No dependency was downgraded/replaced
and pyproject was NOT relaxed. Actual supported-environment execution remains
required locally; QA runner explicitly checks SciPy>=1.14 before tests.

Tests cover known dividend-adjusted prices, call-put parity, IV recovery for calls/
puts over several volatilities, delta/gamma/vega/rho/theta central differences,
Greek parity, units, negative-rate assumption, input/solver bounds and non-escalation.
No skips or relaxed assertions. Numerical tests are NOT native market-data E2E.

Six Gold-reader boundary integration tests supplied, NOT run by assistant. They
REUSE the existing test_gold_quote_reader SQL fixture, which SUBSTITUTES SOURCE
KERNEL. These are explicitly mocked-source SQL integration, NOT full native Bronze/
Silver/Gold E2E. They exercise actual Gold reader invalidation/current-price handling,
reviewed scenario pins, role pins, unknown-time preservation, drift and errors.
No fabricated native replica/harness or mocked numeric result. Full-native synthetic
acquisition-to-analytics acceptance remains an open gate and is not misreported.

No actual repository QA, supported SciPy>=1.14 execution, full native integration,
Ruff, mypy or Windows PowerShell execution here. All Python syntax/line lengths/
trailing whitespace checked. ZIP CRC/exact seven-member set and all six payload
checksums verified; archive SHA256 sidecar independently rechecked.

Review/copy additions, then:

    .\scripts\qa\qa_native_research_options.ps1

Runner verifies expected branch/9442898 ancestry, actual HEAD/status/runtime and
SUPPORTED SciPy version, then focused tests + ALL mandatory QA, fail-fast:

    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

No staging/commit. Untracked whitespace checked separately, preserve unrelated logs.
Suggested commit ONLY after actual local passing QA:
feat(data-platform): compute research IV and Greeks from pinned native Gold prices

No acquisition/live loading/migration/backfills, real identity/governance registration,
publication/trading/strategy cutover. Data-loading hold and platform acceptance gates
unchanged. Future substantive work: audited versioned analytics persistence, explicit
input role/identity/time evidence, eligible publication and native decision replay.
