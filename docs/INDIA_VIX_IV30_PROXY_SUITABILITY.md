# India VIX as an NIFTY 30-day option-IV proxy — research contract

Status: diagnostic evaluator implemented; empirical suitability NOT established.
No publication, decision eligibility, VRP gate change, or trading authority.

## Research question

Does the India VIX observation provide an acceptably accurate and stable proxy
for the platform's NIFTY 30-calendar-day constant-maturity option-surface IV
(`internal_cm`)? The benchmark is the native observational surface output
from `constant_maturity_inputs.build_surface_inputs`, not a nearest-expiry ATM
quote, a stored broker IV/delta, or an EOD VIX close.

The two series must be compared in annualized decimal volatility units. The
signed error convention is:

```
proxy_error = india_vix_iv30 - internal_cm_surface_iv30
```

An error of 0.01 is one annualized volatility point.

## Implemented evaluator

`src/nse_quant/research/india_vix_iv30_suitability.py` exposes
`evaluate_india_vix_iv30_proxy`. It is a pure research diagnostic. It accepts
already-assembled paired observations and validates:

- NIFTY underlying only.
- India VIX and `internal_cm` source identity; surface version and observation
  mode must match the current Black-76 constant-maturity input contract.
- Both source timestamps and receive timestamps are aware, causal, and no later
  than the pair's `as_of`.
- India VIX and surface source timestamps are within 30 seconds by default.
- Positive finite IV values and SHA-256 revision/batch pins.
- Strictly increasing, unique pair `as_of` timestamps; the supplied trade date
  must match the `as_of` calendar date in Asia/Kolkata.

The report includes signed bias, MAE, RMSE, median absolute error, p90 absolute
error, correlation, OLS slope/intercept, and separate chronological calibration
and holdout diagnostics. The default split reserves the latest 30% of complete
trading sessions as holdout, expanding backward as needed to include at least 20
pairs. No trading session is split between calibration and holdout.

Minimum evidence markers are 60 matched pairs, 20 distinct sessions, and 20
holdout pairs. Falling short returns `INSUFFICIENT_EVIDENCE`. Meeting these
minimums returns only `DIAGNOSTIC_ONLY_REVIEW_REQUIRED`; it is not a pass.

## Explicitly not implemented or asserted

- No numeric bias, MAE, RMSE, correlation, or stability acceptance threshold has
  been approved. Do not infer suitability from a high correlation alone.
- The pure evaluator validates pin syntax and the retained condition-artifact
  hash; it does not itself open source stores.
- `src/nse_quant/research/india_vix_iv30_proxy_study.py` now supplies the
  end-to-end source-replay and study-journal workflow. It replays exact VIX
  Bronze/Silver revisions and exact option-chain Bronze/surface Silver variants,
  checks original successful audit availability, and constructs a pair only when
  both source observations were available by the pair's as-of time, remain within
  their freshness limits, and have source clocks no more than 30 seconds apart.
- Pair sets retain the VIX revision, surface observation/digest, source receive
  clocks, source-availability clocks, and exact reviewed market-condition
  artifact bytes. A separate file-backed DuckDB journal stores immutable
  preregistered policy, pair-set and report records with audit jobs.
- `replay_pair_set` reconstructs every pair from its original source stores;
  `replay_evaluation_report` recomputes the report from the pinned pair set.
- The workflow does not establish atomic cross-store snapshots or authenticate
  the issuer of external calendar, forward/rate, or market-condition artifacts.
- A native surface evidence recording/replay implementation exists in
  `data_platform/native_surface_recording.py`, backed by
  `surface_evidence_bundle.py` and the native option-chain Bronze reader. Its
  dedicated native integration tests and the paired-study integration tests are
  committed; operator QA acceptance is still required.
- The recorder retains exact native snapshot pins plus caller-reviewed calendar,
  forward and rate artifact bytes, and recomputes the complete Black-76 bundle on
  replay. It does not authenticate external artifact issuers or provide an
  atomic cross-database snapshot.
- A surface value must not be fabricated from current quotes or reconstructed
  with future information for a historical pair.
- No empirical dataset is bundled and no empirical conclusion is made.
- `suitability_asserted`, `decision_eligibility_asserted`, and
  `publication_asserted` remain false.
- No VRP evaluator or DecisionLoop input is changed.

## Required evidence before a suitability decision

1. Complete operator QA acceptance of the native surface recorder/replay and
   paired-study integration tests. Confirm source pin validation, retained
   premium/forward/rate/calendar evidence, original audit checks and exact replay.
2. Select synchronized NIFTY VIX/surface source revisions. Supply a separately
   reviewed, pinned condition artifact for each pair, tagged from the controlled
   taxonomy: QUIET, NORMAL, ELEVATED_VOLATILITY, EVENT, EXPIRY and STRUCTURAL.
   All six are mandatory for evaluation. The study code does not infer these
   labels or authenticate their issuer.
3. Explicitly choose numeric limits for absolute bias, MAE, RMSE and p90 error
   in annualized decimal-IV units, plus minimum correlation and the OLS slope
   range. Register the immutable policy in the study journal before persisting
   the pair set. There are deliberately no default numerical suitability
   tolerances in code.
4. Persist the pair set using `persist_pair_set`; run `persist_evaluation_report`.
   The report uses a session-isolated chronological holdout and reports both
   aggregate metrics and condition-specific calibration/holdout metrics. Each
   required condition must meet the preregistered minimum holdout pair count.
5. Reproduce the pair set with `replay_pair_set` and the report with
   `replay_evaluation_report`. Review calibration and untouched holdout separately
   for level bias, tail error, correlation, slope/intercept and condition effects.
   Require explicit human research approval; passing numeric checks is not model
   approval and never enables publication or decision use.

Only after a documented model-suitability decision may a separate, versioned
VRP-consumption proposal be considered. That proposal must preserve the charter's
30-day constant-maturity IV definition and the existing fail-closed gate until
its own tests and approval are complete.



## Paired-source study implementation

The offline API is implemented in
`src/nse_quant/research/india_vix_iv30_proxy_study.py`.

1. Create a separate file-backed study database with `initialize_study_store`.
2. Construct a `ProxyAcceptancePolicy` with explicit numeric limits and call
   `register_acceptance_policy`. The returned SHA-256 is the policy ID.
3. For each observation, supply a `ProxyPairRequest` with exact VIX Silver
   revision ID, surface observation ID/digest, and canonical condition-artifact
   bytes plus their SHA-256.
4. Call `persist_pair_set` with four independent read-only source connections
   and the study-store writer. Pair as-of is the latest source availability /
   receive time. Old historical imports that were not available within the
   source freshness window are rejected rather than backdated.
5. Call `persist_evaluation_report`. It reports
   `INSUFFICIENT_EVIDENCE`,
   `HOLDOUT_CRITERIA_NOT_MET_REVIEW_REQUIRED`, or
   `HOLDOUT_CRITERIA_MET_REVIEW_REQUIRED`. None is an approval state.
6. Use `replay_pair_set` and `replay_evaluation_report` with read-only
   connections to reproduce source pairs and the report. Obtain the exact report
   pin with `evaluation_report_sha256(report)`.

The condition artifact is canonical JSON with exactly `source`, `trade_date`,
`as_of`, `available_at`, and sorted `tags`. Its bytes and hash are retained.
A hash establishes byte identity, not issuer authenticity or the correctness of
a condition label. The journal proves that the numeric policy was registered
before the pair set was recorded; it cannot prove that a researcher had never
previously viewed the holdout data.

The workflow remains offline, observation-only and fail-closed. It does not
change the VRP evaluator, DecisionLoop, Gold publication or trading controls.
