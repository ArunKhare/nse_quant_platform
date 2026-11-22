# Document 1: Framework Foundations & Quantitative Measurement Standards

## 1. Scope, Operational Context & Institutional Limitations

The Institutional Options Strategy framework establishes a quantitative, testable architecture designed to classify derivatives market conditions across equity index and single-stock option surfaces. It provides a structured classification crossing implied volatility, term structure, skew, and price-action dynamics.

> **Operational Use Limitation & Risk Notice**
> This manual serves strictly as a derivatives research and quantitative decision-support framework. It does not constitute a trade recommendation or a claim that any cataloged strategy structure is mathematically optimal. In live trading, no strategy is optimal from regime labels alone. Realized expected value depends on the joint conditional return distribution, forward volatility dynamics, jump risk, execution costs, margin rules, taxation, and firm-wide portfolio constraints. Delta bands and days-to-expiration (DTE) ranges represent starting hypotheses requiring instrument-specific calibration.

---

## 2. The Four-Dimensional Market Regime Taxonomy

The classification engine maps market conditions across four structural dimensions, creating a 108-cell regime matrix:

$$\text{Total Regimes} = 2 \text{ (IV States)} \times 3 \text{ (Term Structure States)} \times 3 \text{ (Skew States)} \times 6 \text{ (Price Action States)} = 108$$

The resulting 108 cells represent an objective taxonomy of prevailing derivatives market environments, rather than 108 independent statistical trading edges.

| Layer | State Classifications | Count | Operational Role |
| :--- | :--- | :--- | :--- |
| **Implied Volatility** | High IV; Normal / Low IV | 2 | Base pricing tier and option premium richness |
| **Term Structure** | Contango; Flat; Backwardation | 3 | Calendar slope and inter-temporal variance pricing |
| **Volatility Skew** | Normal; Steep Downside; Forward / Reverse | 3 | Moneyness asymmetry and wing-pricing behavior |
| **Price Action** | Strong Bull; Strong Bear; Range High; Range Low; Compression; High-Vol Chop | 6 | Directional momentum, boundary tests, and realized movement |
| **Combined Surface** | **Full System Matrix** | **108** | **Comprehensive operational classification** |

### 2.1 Implied Volatility State Definitions

The implied volatility layer evaluates current option pricing relative to historical distributions:

* **High IV State:** Implied Volatility Percentile or Implied Volatility Rank typically above 70. Both metrics must be computed and evaluated separately. Options are historically expensive relative to the asset's own history, but may still trade at a discount relative to forecast realized volatility or catastrophic jump risk.
* **Normal / Low IV State:** Implied Volatility Percentile below 70, with extreme low-volatility regimes monitored separately. Represents a lower-premium environment where short option structures often fail to provide adequate compensation for unhedged gamma, discrete rebalancing friction, and jump risk.

#### Quantitative Separation of IV Rank and IV Percentile

Institutional risk systems require separating Implied Volatility Rank (IVR) and Implied Volatility Percentile (IVP), as they measure distinct statistical properties:

$$\text{IV Rank} = \frac{\text{Current IV} - \text{Lookback Minimum IV}}{\text{Lookback Maximum IV} - \text{Lookback Minimum IV}}$$

$$\text{IV Percentile} = \frac{\text{Number of Days with IV} < \text{Current IV}}{\text{Total Days in Lookback Window}}$$

* **IV Rank** measures current implied volatility relative to the historical absolute high-low band. A single extreme outlier compresses IV Rank across the lookback horizon.
* **IV Percentile** evaluates the empirical cumulative distribution, measuring the percentage of trading sessions where volatility traded below current levels.
* Both metrics must be supplemented with realized volatility, forecast volatility models, and the implied-to-realized variance spread.

### 2.2 Term Structure Measurement Standards

Option term structure slope must be derived from synthetic constant-maturity at-the-money (ATM) implied volatility curves rather than unadjusted raw listed expirations:

$$\text{TS} = IV_{\text{ATM}}(30\text{D}) - IV_{\text{ATM}}(90\text{D})$$

* **Contango ($\text{TS} < 0$):** Deferred implied volatility trades above near-term implied volatility. Normal baseline reflecting long-dated hedging demand and cost of carry.
* **Flat ($\text{TS} \approx 0$):** Near-term and deferred implied volatilities are roughly at parity.
* **Backwardation ($\text{TS} > 0$):** Near-term implied volatility trades at a premium to deferred volatility, reflecting concentrated event risk, tail-hedging demand, or systemic market stress.
* Neutral bands must be calibrated to specific instrument liquidity, underlying asset class, and exchange microstructure.

### 2.3 Surface Skew Quantification

Option skew measures moneyness asymmetry across strikes and is quantified via the 25-delta Risk Reversal ($RR_{25}$):

$$RR_{25} = IV(25\Delta \text{ Call}) - IV(25\Delta \text{ Put})$$

* **Conventional Downside Skew ($RR_{25} < 0$):** Out-of-the-money puts trade at a premium to equidistant calls. Standard equity index structure reflecting downside tail-risk pricing.
* **Balanced Wings ($RR_{25} \approx 0$):** Symmetrical smile across both call and put wings.
* **Forward / Reverse Skew ($RR_{25} > 0$):** Out-of-the-money calls trade at a premium relative to puts. Characteristic of supply-constrained commodities or equities vulnerable to acute upward short squeezes.
* Desks must also evaluate the 25-delta butterfly, term-specific skew dynamics, and the underlying asset's historical skew baseline.

### 2.4 Structural Price-Action States

Price-action states establish the path-dependent context for strategy selection:

| State | Structural Description | Quantitative Diagnostics |
| :--- | :--- | :--- |
| **Strong Bull Trend** | Persistent progression of higher highs and higher lows with strong directional efficiency. | Average Directional Index (ADX), regression slope, Kaufman Efficiency Ratio, ATR percentile. |
| **Strong Bear Trend** | Persistent progression of lower highs and lower lows with expanding volatility. | ADX, directional slope, Kaufman Efficiency Ratio, ATR expansion. |
| **Mean-Reverting Range High** | Underlying price tests upper boundary of established range with rejection or failed breakout. | Range boundary test, rejection confirmation, volume exhaustion, localized realized volatility. |
| **Mean-Reverting Range Low** | Underlying price tests lower boundary of established range with support or absorption. | Range boundary test, reversal confirmation, volume profile, localized realized volatility. |
| **Compressed / Coiling Range** | Severe contraction of trading range with declining ATR and compressed realized volatility. | ATR percentile, Bollinger Bandwidth, historical range compression metrics. |
| **High-Volatility Choppy Range** | Wide two-sided moves with weak directional persistence and frequent reversals. | Elevated ATR, low Kaufman Efficiency Ratio, reversal frequency metrics. |

---

## 3. Options Greek Framework & Quantitative Formulations

### 3.1 Greek Risk Sensitivities

| Greek | Long Vanilla Option | Short Vanilla Option | Institutional Risk Role |
| :--- | :--- | :--- | :--- |
| **Delta ($\Delta$)** | Directional sensitivity | Opposite directional sensitivity | Directional exposure and dynamic underlying hedging requirements. |
| **Gamma ($\Gamma$)** | Positive | Negative | Convexity; short gamma positions are vulnerable to market acceleration and overnight gaps. |
| **Theta ($\Theta$)** | Typically negative | Typically positive | Portfolio carry; must be justified against realized movement, jumps, and transaction costs. |
| **Vega ($\nu$)** | Positive | Negative | Sensitivity to surface volatility shifts; dictates vulnerability to volatility crush or expansion. |
| **Vanna** | Spot/volatility cross-derivative | Opposite sign | Measures delta sensitivity to implied volatility; critical during selloffs and skew steepening. |
| **Volga / Vomma** | Typically positive | Typically negative | Convexity with respect to volatility; governs pricing of wings and strangles. |
| **Charm** | Time-decay of delta | Opposite sign | Measures delta drift over time; governs inventory rebalancing as expiration approaches. |

### 3.2 Local Second-Order P&L Taylor Expansion

The local instantaneous P&L approximation for an options position over underlying change $dS$, volatility shift $d\sigma$, and time step $dt$ is:

$$dP\&L \approx \Delta \cdot dS + \frac{1}{2}\Gamma \cdot (dS)^2 + \Theta \cdot dt + \text{Vega} \cdot d\sigma + \text{Vanna} \cdot dS \cdot d\sigma + \frac{1}{2}\text{Volga} \cdot (d\sigma)^2$$

* **Analytical Caveat:** This formulation is strictly a local second-order approximation. It omits higher-order terms, discontinuous price jumps, discrete dynamic hedging drag, dividend adjustments, early exercise, and execution transaction costs. Material shocks require full numerical surface repricing.

### 3.3 Variance Risk Premium (VRP)

The Variance Risk Premium measures implied variance relative to forecast realized variance:

$$\text{VRP} = IV^2 - E[RV^2]$$

* A positive value indicates implied variance trades at a premium to forecast realized variance.
* **Failure Mode Warning:** A positive VRP does not represent an isolated sell signal. Volatility forecasts carry model error, and high implied variance often reflects legitimate compensation for discontinuous jump risks, tail skew steepening, and severe illiquidity.

### 3.4 Expected Move Formulation

The approximate one-standard-deviation expected move ($EM$) over holding duration $\text{DTE}$ is:

$$EM \approx S \times IV \times \sqrt{\frac{\text{DTE}}{365}}$$

* **Worked Example:** For $S = 25,000$, $IV = 15\%$ ($0.15$), and $\text{DTE} = 30$:
  $$EM \approx 25,000 \times 0.15 \times \sqrt{\frac{30}{365}} \approx 1,076 \text{ points}$$
* This calculation represents a statistical dispersion benchmark, not a directional forecast or guaranteed boundary.

### 3.5 Forward Variance Formulation

Evaluating inter-temporal maturity pricing and calendar structures requires calculating forward variance between maturities $T_1$ and $T_2$:

$$\sigma^2_{\text{fwd}} = \frac{\sigma^2(T_2) \cdot T_2 - \sigma^2(T_1) \cdot T_1}{T_2 - T_1}$$

* Desks must evaluate whether deferred volatility is genuinely rich on a forward-starting basis rather than comparing raw listed implied volatility quotes.

---

## 4. Institutional Seven-Layer Research Pipeline & Feature Vector

| Pipeline Layer | Primary Engineering & Analytical Function | System Outputs |
| :--- | :--- | :--- |
| **1. Market Data** | Ingest underlying tick-level OHLCV, option chains, open interest, volume, and futures curves. | Validated, timestamped market snapshots. |
| **2. Volatility Surface** | Construct continuous surfaces, constant-maturity ATM curves, skew risk-reversals, and forward variance. | Clean surface features and maturity metrics. |
| **3. Price Action** | Evaluate trend persistence, ATR percentile ranks, efficiency ratios, range positions, and realized volatility. | Six price-action classifications with confidence scores. |
| **4. Regime Classifier** | Deterministically cross IV $\times$ Term Structure $\times$ Skew $\times$ Price Action states. | Regime ID (e.g., H01, L24), state probabilities, and transition tracking. |
| **5. Candidate Generator** | Generate permissible defined-risk strategy structures matching target delta bands and DTE ranges. | Candidate structures with eligible strikes and expiries. |
| **6. Quantitative Optimizer** | Perform full surface repricing, Monte Carlo simulation, Expected Shortfall, and cost modeling. | Risk-adjusted ranking scores and scenario P&L distributions. |
| **7. Decision & Risk Engine** | Enforce portfolio concentration limits, Greek caps, entry/exit rules, and execution monitoring. | Actionable trade proposals, risk checks, and audit trails. |

### 4.1 Quantitative Feature Set

* **IV Rank & Percentile:** Historical range ratio and empirical CDF rank over 252-day lookback windows.
* **Implied vs. Forecast RV:** Premium valuation metric assessing variance risk premium net of forecast error.
* **Term Slope & Forward Variance:** Constant-maturity slope and forward variance for calendar valuation.
* **25-Delta Risk Reversal & Butterfly:** Skew direction and wing curvature quantification.
* **ATR Percentile & ADX:** Trend persistence and volatility range expansion metrics.
* **Bollinger Bandwidth & Range Position:** Compression indicators and structural boundary tests.
* **Realized Volatility:** Baseline asset movement and conditional volatility forecasts.
* **Portfolio Greeks:** Aggregated delta, gamma, theta, vega, vanna, and volga exposures.
* **Liquidity & Open Interest:** Microstructure filters estimating bid-ask spread drag and market impact.
