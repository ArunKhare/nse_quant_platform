# Institutional regime walk-forward calibration

**Status:** Diagnostic-only implementation  
**Version:** institutional_regime_walk_forward_calibration_v1  
**Underlying:** NIFTY  
**Decision authority:** None

## Purpose

S6 evaluates the provisional thresholds recorded in ouput/research.md sections 3.1–3.5 using chronological rolling train/test windows. It measures threshold stability, out-of-sample state distributions, and HAR-RV forecast error. It does not optimize or replace thresholds.

The implementation deliberately separates:

- Training-window distributions used to describe threshold stability.
- Out-of-sample state distributions using the frozen provisional thresholds.
- HAR-RV forecast-error calibration computed only from each fold's training observations.
- HAR-RV forecast error measured against the subsequent 21-session test horizon.

## Input contract

The runner consumes a prepared NIFTY daily CSV. Each row represents one completed NSE session, ordered by session date, and must contain:

| Column | Meaning |
|---|---|
| session | ISO date of completed NSE session |
| ivp | Daily 30D IV percentile, 0–100 |
| iv30_minus_iv90 | Constant-maturity IV30 minus IV90, annualized decimal volatility |
| rr25 | 30D Black-76 call-25-delta IV minus put-25-delta IV |
| adx14, plus_di14, minus_di14 | Daily Wilder directional diagnostics |
| er20, chop14 | Kaufman efficiency ratio and choppiness index |
| atr14, atr_percentile | ATR and its trailing 252-session percentile |
| bandwidth_percentile | Bollinger BandWidth trailing 120-session percentile |
| range_position | 60-session range position, 0–1 |
| change20, sma20_slope | Directional diagnostics used by price-action classification |
| realized_variance | Daily 5-minute intraday plus overnight realized variance, decimal squared |

The caller is responsible for producing point-in-time features with no future observations, consistent source series, completed sessions, consecutive available NSE-session rows, and valid upstream lineage. The report's two-close persistence follows consecutive available rows; it does not independently reconstruct the exchange calendar or prove that an omitted date was a holiday rather than a data gap. The runner records the CSV SHA-256 and can include an upstream source manifest. It does not fetch data, calculate the IV surface, or reconstruct indicators from raw bars.

## Fold design

Defaults are:

- 360 completed sessions for each rolling training window.
- 63 sessions for each non-overlapping test window.
- 63-session step between folds.
- At least 21 test sessions are required for the 30-calendar-day HAR-RV forecast comparison.
- HAR-RV uses the existing 252-session model training window and 21-session forecast horizon.

The training window must be at least 324 sessions so the existing rolling-origin HAR-RV calibration can reach its 30-origin sufficiency threshold. Each fold's test starts strictly after its training end. Overlapping test windows are rejected to avoid double-counting observations in aggregate out-of-sample distributions.

## Evaluated provisional rules

- IV state: HIGH_IV entry at IVP 70 and exit below 60.
- Term structure: flat when absolute IV30–IV90 is at most 0.005 (0.5 volatility points).
- Skew: high-put threshold at the trailing 252-session RR25 10th percentile, with 50th-percentile exit hysteresis recalculated point-in-time; positive RR25 is forward/reverse skew.
- Price action: frozen ADX, ER20, CHOP, ATR percentile, BandWidth percentile, and range-position rules from the v5 classifier.
- HAR-RV: training-only rolling-origin forecast-error calibration and a separate 21-session out-of-sample forecast comparison.

For each fold, the report provides training quantiles (p10/p25/p50/p75/p90), fixed provisional cutoffs, out-of-sample state counts/fractions, unavailable price-action observations, price-action confidence quantiles, HAR-RV calibration sufficiency, and out-of-sample annualized variance forecast error.

## Run

    uv run python scripts/run_institutional_regime_calibration.py --input data/research/nifty_regime_calibration.csv --source-manifest data/research/nifty_regime_sources.json --output reports/research/institutional_regime_calibration.md

The runner writes Markdown and a same-basename JSON report. A report with insufficient or invalid evidence exits with status 2. The CSV and manifest paths above are examples; use the governed, source-pinned NIFTY research export.

## Governance constraints

- thresholds_changed and thresholds_promoted remain false.
- decision_eligibility_asserted and paper_trading_approval_asserted remain false.
- The HAR-RV calibration's internal gate-margin eligibility is suppressed in this report; sufficiency is retained only as a review diagnostic.
- No classifier settings, strategy gates, risk limits, published Gold artifacts, or paper/live permissions are modified.
- Any proposed threshold change requires a separate review of the complete report, explicit rationale, a versioned configuration/classifier update, and fresh out-of-sample validation.
