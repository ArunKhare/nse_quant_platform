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
- The evaluator does not authenticate or replay the pinned source artifacts.
  Pins are syntax-checked only.
- It does not establish historical availability, atomic cross-store snapshots,
  session completeness, or source authenticity.
- Durable, replayable option-surface evidence recording is still outstanding.
  A surface value must not be fabricated from current quotes or reconstructed
  with future information for a historical pair.
- No empirical dataset is bundled and no empirical conclusion is made.
- `suitability_asserted`, `decision_eligibility_asserted`, and
  `publication_asserted` remain false.
- No VRP evaluator or DecisionLoop input is changed.

## Required evidence before a suitability decision

1. Implement separately governed durable option-surface evidence capture and
   replay, including premium quotes, forward/rate evidence, expiry-close
   calendar reference, exact source/receive clocks, and immutable source pins.
2. Produce synchronized NIFTY pairs from the same observation window; enforce
   the 30-second maximum source-time gap and point-in-time availability.
3. Run the evaluator over a sufficiently broad period covering quiet, normal,
   elevated-volatility, event, expiry and structural market conditions.
4. Review calibration and untouched chronological holdout separately. Report
   bias, MAE/RMSE, tail error, correlation, slope/intercept, and regime/session
   breakdowns. Check for systematic level bias and volatility-state dependence.
5. Pre-register business tolerances and acceptance criteria before inspecting
   holdout results. Require an explicit human research decision; no automatic
   suitability promotion is supported by this module.

Only after a documented model-suitability decision may a separate, versioned
VRP-consumption proposal be considered. That proposal must preserve the charter's
30-day constant-maturity IV definition and the existing fail-closed gate until
its own tests and approval are complete.
