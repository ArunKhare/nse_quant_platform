Stage 1 Open Decisions and Platform Label Standardization
Repository state examined: ArunKhare/nse_quant_platform, branch feat/medallion-feature-store, commit bf18386.
Authority: docs/IMPLEMENTATION_CHARTER.md (concluded). This document does not reopen the charter. It records evidence for each open parameter and flags only the places where code disagrees with the charter.

Status of every threshold below: provisional default, to be calibrated walk-forward on NIFTY data before any of it influences paper decisions. Paper-only mode, decision_eligibility_asserted = false, and the four-component regime are unchanged.

1. Decision summary
#	Decision	Recommendation	Basis
D1	IV state metric	Use IV Percentile (IVP) over 252 trading days of daily 30D constant-maturity IV. HIGH_IV when IVP ≥ 70. Log IVR alongside it and flag divergence above 30 points.	IVP uses all 252 days, while IVR uses only the high and low, so one spike distorts IVR for months (FlashAlpha)
D2	Term structure	TS = IV30 − IV90, both constant-maturity, using linear interpolation in total variance. Interpolate only, never extrapolate. Exclude expiries under 7 days.	India VIX interpolates near and next month to 30 days (
NSE white paper
). Carr–Wu interpolate the two nearest maturities to 30 days and do not extrapolate (Carr & Wu).
D3	Skew	RR25 at 30D constant maturity, measured relative to its own 252-day history. Retire the v4 ATM put−call measure.	Practitioners measure NIFTY skew as 25Δ put IV − 25Δ call IV (OI Data). Extremes are defined by the 90th percentile over a 1-year lookback (Quantsapp).
D4	Price action v5	Six charter states from daily bars: ADX14, Kaufman ER, CHOP14, ATR percentile, BandWidth percentile, and range position. Add hysteresis and a confidence score.	See section 3.4
D5	VRP inequality	Strict > as the charter says. The code currently uses >=.	Charter section 7: VRP = IV² − E[RV²] > 0
D6	E[RV²] estimator	HAR-RV forecast of 30-day variance, built from 5-minute intraday RV plus the overnight return. Trailing 20-day RV stays only as a logged fallback.	HAR-RV (Corsi); VRP is defined against a forecast of expected variance, not the realized variance (Zhou, FEDS 2010-14)
D7	VRP margin	Keep minimum_vrp configurable (default 0) and add a margin based on forecast error after calibration.	NIFTY VRP was positive on 79.5% of days from 2016 to 2024, so > 0 alone filters little (India VRP study)
D8	Interim IV30 source	Use India VIX as the IV30 input to VRP and IVP until the internal constant-maturity surface exists. Never mix it with ATM IV in one series.	India VIX is NSE's 30-day constant-maturity figure built from near and next NIFTY expiries (
NSE
)
D9	Strong-trend label spelling	Follow the charter: STRONG_BULL_TREND / STRONG_BEAR_TREND. The registry currently has STRONG_BULL / STRONG_BEAR.	The charter is concluded, and playbook headings read "Strong Bull Trend"
2. Label audit: where each vocabulary lives and why
The platform has seven distinct label vocabularies. Only one of them is the institutional regime. The rest exist for historical or diagnostic reasons. The problem is not that several vocabularies exist. It is that some of them share field names (regime, allowed_regimes) and token spellings (TREND_UP, FLAT, HIGH_PUT_SKEW) with the canonical one.

#	Vocabulary	Where it is produced	Where it is stored	Who consumes it	Why it exists	Conflict with canonical
V1	Canonical 108 labels: {HIGH_IV,LOW_IV}_{CONTANGO,FLAT_TERM,BACKWARDATION}_{NORMAL_SKEW,HIGH_PUT_SKEW,FORWARD_REVERSE_SKEW}_{6 price-action}	core/regime_registry.py (generated, not hand-typed)	config allowlist, eligibility decisions, decision_audit	settings validators, resolve_effective_regimes, strategy eligibility	Charter section 6: the single source of truth	Strong-trend spelling differs from the charter (D9)
V2	v4 institutional components: HIGH_IV/NORMAL_IV, CONTANGO/FLAT/BACKWARDATION, HIGH_PUT_SKEW/HIGH_CALL_SKEW/NORMAL_SKEW, TREND_UP/TREND_DOWN/RANGE_UPPER/RANGE_MIDDLE/RANGE_LOWER/INSUFFICIENT_DATA	research/evidence_plugins/institutional_regime.py, institutional_regime_skew.py, institutional_regime_price_action.py (institutional_iv_term_components_v4)	institutional_regime_observations, decision evidence	eligibility (regime_label)	Stage 0 intraday research classifier	Four token mismatches: NORMAL_IV≠LOW_IV, FLAT≠FLAT_TERM, HIGH_CALL_SKEW≠FORWARD_REVERSE_SKEW, and all price-action tokens. Its composite label can never match the registry, so IC eligibility rejects every cycle. That is a correct fail-closed result, but it is caused by vocabulary, not by market state.
V3	Daily IV research regime: LOW_IV/NORMAL_IV/HIGH_IV × term ±0.25 × HIGH_PUT_SKEW/CALL_SKEW/NORMAL_SKEW (3 parts)	research/iv_regimes.py, scripts/classify_iv_regimes.py, run_milestone2_research.py	daily_iv_regime	strategy/regime_policy.py:73 (latest_daily_iv_regime)	Milestone 2 research	Three components with three IV levels. Same token spellings, different meaning.
V4	Legacy daily market regime: BULL\|NORMAL, RANGE\|HIGH, … (SMA/ATR on daily)	research/regimes.py::combine_regime, scripts/build_daily_market_regimes.py	market_regimes (trend_regime, volatility_regime, iv_regime, regime), data-platform legacy bronze/silver/gold	trade_outcomes.py → learned regime_policy.py → regime_policies.allowed_regimes → regime_risk_policy.py → decision_loop._apply_regime_limits; regime_coverage_report.py; walk_forward_regimes.py	Original learned-policy and risk-limit pipeline	The charter forbids these as regime labels. bf18386 already demoted them to market context for eligibility, but risk-limit lookup is still keyed on them.
V5	core.models.MarketRegime: TREND_UP/TREND_DOWN/RANGE/VOLATILE/UNKNOWN	calculations.classify_market_regime (SMA20/50 on 1-minute closes)	features.regime	SpotFeatureGate, UI	Intraday feature for entry gates	It is a field called regime that is not a regime, and it shares TREND_UP with V2
V6	Spread-profile tags: TREND, HIGH_VOL, BULLISH, BEARISH	research/spread_profiles.py (allowed_regimes)	profile config	spread strategy research	Early vertical-spread research	Uses the allowed_regimes field name with non-canonical tokens
V7	Evidence states: BULLISH/BEARISH/MIXED, UP/DOWN/FLAT, NEUTRAL, HH_HL/LH_LL/BULLISH_BOS, RISING/FALLING/FLAT	mutli_timeframe.py, technical_indicators.py, market_structure.py, volume_flow.py	decision evidence rows	timing filter, audit	Evidence plugins: legitimately not regimes	Acceptable if namespaced. FLAT collides textually with V2.
Other places that carry labels:

UI: ui/dash_app.py shows current_regime, regime_source and allowed_regimes without saying which vocabulary they come from.

Tests: test_live_snapshot_eligibility.py (NORMAL_IV_CONTANGO_NORMAL_SKEW), tests/research/test_regime_policy.py, test_active_policy_export.py, and test_decision_loop_position_monitoring.py (RANGE|HIGH) encode non-canonical labels as if they were regimes.

3. Evidence behind each decision
3.1 IV state (D1)
The v4 classifier is wrong: it computes IV rank over the last 250 intraday observations, which covers days, not the 252 trading days the framework specifies. Because the window is so short, IV rank measures intraday drift.

Why IVP: IVP counts how many of the 252 days fell below today's level. IVR uses only the 52-week high and low, so a single spike can make current IV look artificially low for months (FlashAlpha). The framework doc already asks for IVR and IVP to be computed separately with a 70 threshold.

Proposed rules:

Input: one end-of-day IV30 observation per trading day.

Classification: HIGH_IV at IVP ≥ 70. Exit HIGH_IV only when IVP < 60 (hysteresis).

Minimum history: 120 daily observations. With less, there is no IV-state component and therefore no regime label (fail closed).

Divergence: when |IVR − IVP| > 30, record it as a diagnostic, not a gate (FlashAlpha).

Bootstrapping: India VIX has a long public daily history, so IVP can be seeded immediately (D8). Once the internal IV30 exists, run both side by side, then switch over. Use one source per series.

3.2 Term structure (D2)
Market structure: NSE lists NIFTY options with 4 weekly, 3 consecutive monthly, 3 quarterly (Mar/Jun/Sep/Dec) and 8 semi-annual expiries (NSE NIFTY 50 F&O). A 90-day point is therefore always bracketed by listed expiries, so interpolation is possible without extrapolation.

Expiry calendar:

SEBI limits each exchange's equity-derivative expiries to Tuesday or Thursday and allows one weekly benchmark contract (SEBI circular, 26 May 2025).

NIFTY weekly and monthly contracts have expired on Tuesday since 1 September 2025 (Economic Times).

Historical data before that date has Thursday expiries, so the time-to-expiry calculation must read the actual expiry date of each contract and never assume a weekday.

Method:

Measure time in minutes to the 15:30 expiry close, divided by 525,600, as India VIX does (
NSE white paper
).

Interpolate linearly in total variance
𝜎
2
𝑇
σ
2
 T between the two expiries bracketing the target. Use the same approach as Carr–Wu at 30 days, with no extrapolation (Carr & Wu).

Exclude expiries with fewer than 7 calendar days to go. This follows the 7-day minimum used in the India VRP study and the Quantsapp skew definition. India VIX itself rolls 3 trading days before expiry (
NSE
).

Data gap: expiries_per_snapshot: 2 in both settings files captures only the near and next weekly expiries, so neither 30D nor 90D can be built today. Capture must be widened to every expiry up to the first one beyond 90 days, which is about 6–7 expiries.

Flat band:

VIX/VIX3M is in contango on about 92% of days since 2010, and its flat state is the single value 1.00 (StockPriceAlerts). Mature markets offer no evidence-based fixed band.

Provisional rule: FLAT_TERM when |IV30 − IV90| ≤ 0.5 vol points. Then recalibrate the band so that FLAT_TERM covers a stated share of history (for example, the central 20% of the TS distribution) using in-sample windows only.

The v4 tolerance of 0.002 (0.2 vol points) on near-vs-next weekly IV is a different quantity and should not carry over.

Sign: contango means TS < 0 under the charter definition (IV30 < IV90).

3.3 Skew (D3)
The v4 measure is not skew:

v4 computes ATM put IV − ATM call IV at the same strike. Under put–call parity these should be equal, so the gap mostly reflects the forward or dividend/basis error in the IV solver, not the shape of the smile.

It also has no 25Δ wings. NIFTY's ordinary state is puts richer than calls (OI Data), so a fixed 0.03 cut can misclassify normal days.

Proposed measure: RR25 at 30D constant maturity, using the charter sign convention IV(25Δ call) − IV(25Δ put). The normal NIFTY state is negative under this convention.

Bands, using the 252-day history of RR25:

HIGH_PUT_SKEW: RR25 at or below its 10th percentile, which is the mirror of Quantsapp's 90th-percentile put−call extreme with a 1-year lookback and at least 40 readings (Quantsapp). Exit when it rises above the 50th percentile (hysteresis, as in the same source).

FORWARD_REVERSE_SKEW: RR25 > 0, an absolute sign change. Calls priced over puts is described as the rarer upside-chasing state (OI Data).

NORMAL_SKEW: everything else.

Delta convention: Black-76 on the matching futures or synthetic forward, with the 25Δ strike found by interpolating IV in delta space. Record the convention in classifier_version.

3.4 Price action v5 (D4)
Timeframe: the IC holding period runs from weeks to a month, so the classifier runs on completed daily bars. Do not include the partial intraday bar, which is a v4 defect. Intraday data only feeds the 5-minute RV used in D6.

Diagnostics: these follow the framework doc's own list.

Diagnostic	Standard definition	Evidence for thresholds
ADX(14)	Wilder smoothing	> 25 strong trend, < 20 no trend, 20–25 indeterminate (Investopedia)
Kaufman ER(20)
∣
𝐶
𝑡
−
𝐶
𝑡
−
20
∣
/
∑
∣
Δ
𝐶
∣
∣C
t
​
 −C
t−20
​
 ∣/∑∣ΔC∣	No universal cut; judge against the instrument's history (LuxAlgo). The random-walk noise floor is about
1
/
𝑁
1/
N
​
 : 0.32 at N=10 and 0.22 at N=20 (Alpha Strategic Growth).
CHOP(14)	Dreiss choppiness index	> 61.8 choppy, < 38.2 trending; conventional, not tested rules (Trading Defined)
ATR(14) percentile	Rank over 252 days	Instrument-relative
BandWidth(20, 2) percentile	(upper − lower)/middle	A squeeze is a reading at or below the 5th percentile of the last 120 bars; it signals low volatility, not direction (Quantzee)
Range position	(C − L60)/(H60 − L60)	Defines "Range High" and "Range Low" as tests of the upper or lower boundary (framework doc section on price action)
Provisional rules, evaluated in priority order (first match wins):

HIGH_VOL_CHOP: ATR pct ≥ 70 and (ADX < 20 or CHOP > 61.8) and ER20 < 0.22, i.e. at the noise floor.

STRONG_BULL_TREND / STRONG_BEAR_TREND: ADX ≥ 25 and ER20 ≥ 0.35 (about 1.6× the noise floor), with direction set by the sign of the 20-day change and SMA20 slope. The sign of +DI − DI must agree.

COMPRESSION: BandWidth pct ≤ 10 over 120 bars and ATR pct ≤ 30.

RANGE_HIGH: range position ≥ 0.5. RANGE_LOW: range position < 0.5. Both require ADX < 25.

Three things apply to all of the rules:

Hysteresis: a new state must persist for 2 consecutive closes before the label changes, and each entry threshold has a matching exit threshold (for example, ADX enters a trend at 25 and leaves it at 20). Requiring persistence and a minimum dwell time stops labels from flipping on every bar (Kiploks).

Confidence: take the minimum normalized distance of the deciding diagnostics from their thresholds, scaled to 0–1. The framework doc requires "six price-action classifications with confidence scores". Below a configurable floor, emit no price-action component, so there is no label and eligibility fails closed.

Calibration: fit thresholds on in-sample windows only and apply them out of sample. Version every change through classifier_version (Kiploks).

3.5 VRP (D5–D8)
Definition and sign: VRP is the risk-neutral expectation of variance minus the physical conditional expectation, with implied variance minus a forecast of realized variance as the proxy (Zhou, FEDS 2010-14). Carr–Wu use the opposite sign (RV − SW) and find it significantly negative for the S&P 500: a mean log premium of −0.594 with t = −9.48 (Carr & Wu). The charter's IV² − E[RV²] matches the Zhou sign.

Forecast, not trailing:

The playbook allows an IC in High-Volatility Chop "only if IV > forecast RV".

Zhou builds E[RV] from an AR(12) forecast of realized variance, using 5-minute intraday returns plus the close-to-open return (FEDS 2010-14).

HAR-RV regresses next-period log RV on its daily, 5-day and 22-day averages and is fitted by OLS with Newey–West errors in its extended form (Corsi).

The platform already stores 1-minute spot candles, so it can build 5-minute RV now.

Proposed method:

Compute daily RV as the sum of squared 5-minute log returns plus the squared overnight return.

Fit HAR on a rolling window and forecast variance over the next 30 calendar days.

Annualize consistently with IV30.

Keep the current trailing 20-day close-to-close RV only as a logged fallback with estimator="trailing_close_close". In decision mode, the fallback cannot pass the gate.

Inequality: variance_risk_premium.py:89 uses >=. The charter says > 0, so change it to strict >. A tie at exactly zero is measure-zero in practice, but the code should match the charter text.

Margin:

NIFTY VRP was positive on 79.5% of trading days from Jan 2016 to Jul 2024. It turned sharply negative on shock days (COVID −0.93, Election 2024 −0.93) and mean-reverted within 5–10 days (India VRP study). A separate Indian study also finds a significantly positive premium using India VIX (Journal of Economic Sciences).

A zero threshold therefore admits most days. Keep minimum_vrp = 0 now, and after calibration set it to k × the HAR forecast's out-of-sample RMSE (in variance units), choosing k walk-forward.

Interim IV30 (D8):

The current gate uses features.atm_iv, which is the near-weekly ATM IV. That is the wrong horizon: it can be under 7 days and include expiry-day effects.

India VIX is NSE's own 30-day constant-maturity measure, built from near and next NIFTY expiries with a 30%-spread quote filter and MIBOR rates (
NSE white paper
). It is the closest observable to the charter's IV.

Caveat: India VIX is model-free variance across the whole strike strip, so it typically sits above ATM IV. Use it consistently for both VRP and IVP until the internal IV30 replaces it, and record iv_source in the audit.

4. Standardization plan
4.1 Principle
One meaning per field name: the fields regime, regime_label and allowed_regimes may only ever hold V1 labels.

Rename the others: every other vocabulary becomes a context or evidence field with an explicit namespace, so it can no longer be read as a regime.

4.2 Target namespaces
Namespace / field	Vocabulary	Replaces
regime_label, allowed_regimes	V1 canonical 108 only	—
regime_components.{iv_state,term_structure,skew,price_action}	Registry enums IvState, TermStructure, Skew, PriceAction	V2 tokens
market_context.daily_trend_vol	V4 BULL\|NORMAL etc.	market_regimes.regime, regime_policies.allowed_regimes (legacy)
features.intraday_shape	V5 TREND_UP/…	features.regime
research.iv_daily_state	V3	daily_iv_regime.regime_label
spread_profile.market_tags	V6	spread_profiles.allowed_regimes
evidence.<plugin>.state	V7	unchanged (already plugin-scoped)
4.3 Concrete changes (proposed, not yet applied)
Registry: rename PriceAction.STRONG_BULL/STRONG_BEAR to STRONG_BULL_TREND/STRONG_BEAR_TREND, per the charter (D9). The six IC labels do not contain either token, so the allowlist is unaffected. Bump REGIME_REGISTRY_VERSION to v2.

v4 adapter (immediate, no market logic change): add one explicit mapping for the IV, term and skew components only: NORMAL_IV→LOW_IV, FLAT→FLAT_TERM, HIGH_CALL_SKEW→FORWARD_REVERSE_SKEW. v4 price-action tokens get no mapping, as the charter requires ("must not be silently reinterpreted"). That leaves the label None until v5 ships. The semantics are still v4's (wrong IVR window, ATM-parity skew), so mark the component provenance v4_research and keep it out of eligibility.

v5 classifier: a new institutional_regime_v5 implementing sections 3.1–3.4. It emits registry enums directly, plus per-component confidence and inputs.

Risk limits: re-key regime_risk_policy and _apply_regime_limits on V1 labels. Until learned V1 policies exist, use the static config limits; do not look up by legacy V4 strings. This closes the remaining open item from bf18386.

Field renames:

Rename features.regime → features.intraday_shape and spread_profiles.allowed_regimes → market_tags.

For one version, keep deprecated read-only aliases (properties) so persisted rows and the UI keep working.

Persistence:

Add the column regime_vocabulary (canonical_v1, legacy_daily_v0, iv_daily_v0) to market_regimes, regime_policies, daily_iv_regime and institutional_regime_observations. Backfill it from known producers.

No destructive migration: old tables stay, which satisfies "do not delete existing safety controls".

Guard test:

Add a test that walks every regime_label / allowed_regimes writer and asserts registry membership.

Add a static check (ruff custom rule or a test that greps src/) that rejects the literals BULL|, BULLISH, BEARISH and MIXED in regime fields.

Tests: move the four test files listed in section 2 to canonical labels, or rename their fixtures to market_context.

UI: show regime_label (canonical), market_context and intraday_shape as three separately labelled fields.

Housekeeping: delete the duplicate framework-foundations-quantitative-measurement (1).md and fix the 36 typo'd ..._REVERSE_SKEW_REVERSE_SKEW codes in INFO/108-regime-strategy-playbook-v2.md.

4.4 Sequencing
Step	Scope	Unblocks
S1	Items 1, 2, 7, 8, 10, plus the > fix (D5)	Label consistency; no market logic changes
S2	Widen expiry capture; constant-maturity IV30/IV90; RR25; India VIX ingest as interim IV30	D2, D3, D8
S3	5-minute RV + HAR forecast in the VRP gate	D6, D7
S4	v5 price-action classifier + hysteresis + confidence	D4; first non-None canonical labels
S5	Re-key risk limits; field renames; UI	Items 4–6, 9
S6	Walk-forward calibration report for all provisional thresholds	Replacing the provisional values
5. Decisions recorded (22 Nov 2026)
Legacy retirement.

Decision: the platform is moving off the legacy system to a charter-based medallion architecture.

D9: resolved in favour of the charter spelling (STRONG_BULL_TREND / STRONG_BEAR_TREND).

Section 4.3 changes from "namespace and alias" to "retire":

V3 (daily IV research regime), V4 (legacy daily regime) and V6 (spread-profile tags) leave the decision path entirely. Their tables become frozen, read-only legacy bronze until they are deleted.

No compatibility aliases are added.

V5 (features.regime) is renamed, not aliased.

Risk limits are re-keyed on canonical labels only.

India VIX accepted as interim IV30, with the horizon caveat resolved below.

5.1 Horizon: swing/intraday platform vs a 30-day IV
What India VIX is: NSE computes it live during market hours. It uses the near and next monthly NIFTY expiries, not the weekly Tuesday series, interpolated to 30 days. It rolls 3 trading days before expiry (
NSE white paper
,
Trade Pulse
). It reacts only partly to weekly-expiry moves, so weekly traders should read their own expiry's IV (
QuantPower
).

What the charter IC trades: the master manual's iron condor is not a weekly or intraday trade. It specifies 25–40 DTE entries, a 50% profit target, a 21 DTE time stop, and E[RV²] over the 30-day holding period (IRON_CONDOR_MASTER_MANUAL.md section 6). For this strategy, India VIX matches the horizon. The current config is the mismatch:

min_days_to_expiry: 1

expiries_per_snapshot: 2 (weeklies only)

The rule this implies, at two layers:

Regime layer (structural, strategy-agnostic): always 30D/90D constant maturity and daily bars, as the charter requires. This gives one canonical label per day for every strategy, so labels are comparable across strategies and time.

Entry layer (strategy-specific): each strategy profile declares its own vrp_horizon and traded-expiry IV.

IC (charter): IV30 against the 30-day E[RV²]. India VIX now, and the internal constant-maturity IV30 later.

Future weekly or intraday strategies: the IV of the traded expiry against the HAR forecast to that expiry. They would be added through the charter's strategy-onboarding process, not by changing the IC gate.

Intraday use of India VIX:

Feed the live India VIX into the VRP gate on each cycle, with the HAR forecast refreshed daily.

Feed only the daily close into IVP, so the 252-day history has a consistent sampling point.

Record the monthly-roll discontinuity and the 9:15–15:30 publication window as data-quality flags.

Medallion placement:

bronze: raw India VIX ticks plus NSE's end-of-day file.

silver: validated 1-minute bars and the daily close.

gold: the iv30 feature, with iv30_source = india_vix | internal_cm, so the switch to the internal constant-maturity IV30 is a single configuration change with an audit trail.

5.2 Open items
Align the IC profile with the master manual: entry 25–40 DTE on monthly expiries, a 21 DTE time stop, and a 50% profit target. Widen expiry capture to cover 90D.

Start S1 (revised for retirement) on feat/medallion-feature-store.

## 6. S1/S2 implementation status — 25 Nov 2026

This is a status addendum, not a charter amendment. It supersedes the historical
"Start S1" instruction at the end of section 5.2 without rewriting the original
research baseline, provisional thresholds or the section 5 retirement decision.
Research substeps S1/S2 are not the charter's numbered implementation stages.

### S1 — Complete (owner-reported label-test acceptance)

The platform owner reported that all tests passed with the new canonical labels.
Record S1 label standardization as complete on that basis. No independent test
count, exact test command or local validation commit accompanied that report.
This does not assert completion of every broader Stage 1 deliverable or paper
validation. IMPLEMENTATION_CHARTER.md has not been changed by this addendum.

### S2 — In progress (implementation present; acceptance not closed)

Repository inspected: ArunKhare/nse_quant_platform, branch
feat/medallion-feature-store, commit
299523647d2810f0a433a5fb53772aebf665e59f.

Implemented S2 increments recorded through that baseline:

- Constant-maturity Black-76 IV30/IV90 and call-minus-put RR25 input components,
  with explicit forward/calendar evidence and no extrapolation.
- Horizon capture selection and a REST provider horizon-acquisition path.
- India VIX acquisition/normalization, native Bronze/Silver retention and replay.
- Surface evidence bundles and a reviewed observation journal, including retained
  input-quality rejection, audited variants and conflict quarantine.
- EOD-file history and native VIX minute-bar builders.
- Audited series materialization, exact retries, independent read-only replay,
  interrupted-write checks and explicit offline CLI orchestration.

The next tranche supplied alongside this addendum adds pinned read-only IV30
feature retrieval: EOD IVP/IVR research statistics, actual-quote-clock live VIX
freshness checks and parent-materialization availability cutoffs. It keeps EOD
and live inputs separate and does not mix india_vix with internal_cm history.
Applying that code is not evidence that its native integration tests passed.

Validation evidence is intentionally bounded:

- Owner-reported S1 new-label test acceptance is recorded above.
- Previous materialization tranche: 24 isolated tests passed using Python 3.12.14,
  DuckDB 1.2.2 and pytest 8.3.5; not the full Windows checkout.
- New feature tranche: 25 isolated arithmetic/policy/planning tests passed with
  the pinned EOD parser; native reader integration tests are supplied separately
  and are not reported as passed.
- No new complete Windows/Python 3.14/DuckDB 2.0 run, full lint/type report,
  paper-validation result or Quack operational integration pass has been supplied
  with this status update. A commit message is not validation evidence.

S2 closure remains pending:

1. Execute native surface, native minute-materialization and feature-reader tests
   in the actual checkout; record the command, commit and results.
2. Confirm captured data—not just expiry selection—supplies usable 30D/90D and
   25-delta brackets, matching forwards/rates, genuine quote clocks and retained
   calendar provenance; retain rejected observations where quality fails.
3. Validate acquisition/import orchestration and history coverage. Supplied-row
   counts do not certify exchange-session completeness or source authenticity.
4. Complete any explicitly required Gold admission/publication and downstream
   integration without treating research evidence as decision-ready authority.
5. Run relevant regression, lint/type and paper-validation selections and retain
   the evidence before declaring S2 accepted.

S3 (HAR-RV), S4 (v5 classifier validation), S5 (canonical risk/UI integration)
and S6 (walk-forward calibration) are not marked complete by this addendum.
The IC monthly-entry/time-stop/profit-target alignment remains a separate closure
check unless separately demonstrated by configuration and tests.

Paper-only controls, decision_eligibility_asserted=false, canonical four-component
regimes and single-writer ownership remain unchanged. No runner cutover, live
activation, implicit EOD-to-live fallback or automatic Gold promotion is authorized.

### S3 estimator gate hardening — historical gate-contract baseline

The VRP evaluator now distinguishes numeric diagnostic availability from estimator
eligibility. The trailing close-to-close RV implementation is explicitly tagged
`trailing_close_close`, `diagnostic_only`, and `gate_eligible=false`. A
positive arithmetic VRP computed from that fallback cannot pass the hard gate.

The gate contract records the required HAR-RV identity: 30-day forecast horizon,
5-minute intraday squared log returns plus squared overnight return, and a
versioned estimator identifier. The evaluator checks the declared identity but
does not fit, validate, or produce a HAR model. The live decision-loop path still
supplies the trailing fallback, so it now fails closed with the distinct
`variance_risk_premium_estimator_not_gate_eligible` rejection reason. Estimator
identity and eligibility are retained in decision evidence and audit output.

This is a safety correction, not completion of S3. The 5-minute RV construction,
overnight-return alignment, rolling HAR fit, 30-calendar-day forecast, point-in-time
model validation and forecast-error calibration remain unimplemented. The current
decision-loop IV input is also still near-expiry ATM IV rather than the charter's
30-day India VIX/internal constant-maturity input; that D8 integration remains open.

This section records the earlier gate-only state before the HAR-RV implementation
below. Its statements that the HAR-RV pipeline remains unimplemented and that
the decision loop supplies trailing RV are superseded by the subsequent
implementation addendum. The D8 30-day IV-source limitation remains open.


## S3 HAR-RV implementation tranche — 2026-11-25

Implementation status: code added; local acceptance pending.

- Added `research/har_realized_volatility.py` with a point-in-time RV observation builder and a rolling HAR-RV level-OLS model.
- RV observations are built from the canonical 1-minute spot-candle series. Each regular NSE session must contain exactly 375 unique minute bars from 09:15 through 15:29 IST. Missing bars, duplicate timestamps, invalid prices, incomplete sessions, and unavailable predecessor sessions are not bridged.
- Intraday variance is the sum of squared log returns over 75 five-minute observations. The first five-minute return is measured from the session open; later returns use successive five-minute closes. Overnight variance is the squared log return from the previous complete session close to the current session open.
- HAR predictors are daily RV, trailing five-session mean RV, and trailing 22-session mean RV. The model uses a rolling 252-observation OLS fit and recursively forecasts 21 regular sessions as the 30-calendar-day approximation. The reported forecast is annualized volatility, sqrt(mean forecast daily variance × 252), for comparison with annualized 30-day IV.
- Added rolling-origin 21-session forecast-error calibration, reporting the 90th-percentile absolute annualized-variance error when at least 30 out-of-sample origins are available. When eligible, that p90 error is added to the configured minimum VRP as a variance-unit safety margin. If calibration is unavailable, HAR-RV is not gate-eligible.
- Decision-loop evidence now uses HAR-RV only. The former trailing close-to-close estimator is retained as an explicitly unused diagnostic fallback.
- The VRP gate now separately validates the HAR-RV estimator identity, calibration eligibility/margin, and implied-volatility input identity. The current near-expiry ATM IV is not 30-day constant maturity, so the gate remains fail-closed even when a valid HAR-RV forecast is available. D8 India VIX EOD / internal constant-maturity IV integration remains a separate required step.
- The live loop reads only completed historical 1-minute candles from its existing operational store and caches the prior-session forecast/calibration by instrument and trading date, avoiding a 550-day query and HAR refit on every 15-second cycle. It does not run Medallion transformations or synchronously build Silver/Gold artifacts.

Validation required on the operator's Windows environment:
- `uv run pytest -q tests/research/test_har_realized_volatility.py tests/test_variance_risk_premium.py tests/strategy/test_decision_loop.py`
- `uv run ruff check src/nse_quant/research/har_realized_volatility.py src/nse_quant/research/variance_risk_premium.py src/nse_quant/strategy/decision_loop.py tests/research/test_har_realized_volatility.py tests/test_variance_risk_premium.py tests/strategy/test_decision_loop.py`
- `uv run mypy src/nse_quant/research/har_realized_volatility.py src/nse_quant/research/variance_risk_premium.py src/nse_quant/strategy/decision_loop.py`

No claim of test or QA acceptance is made until those commands pass.
