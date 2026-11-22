# Document 3: Strategy Structures, Execution Risks & Market Controls

## 1. Strategy Construction & Payoff Geometry

Institutional options trading relies on defined-risk structures where payoff boundaries, maximum drawdown, and capital commitment are strictly quantified prior to trade initiation.

| Structure Name | Structural Leg Construction | Maximum Profit & Maximum Loss Formulations | Typical Institutional Use Case |
| :--- | :--- | :--- | :--- |
| **Bull Call Debit Spread** | Buy higher-delta (ITM/ATM) call; sell lower-delta (OTM) higher-strike call. | **Max Loss:** Net debit paid.<br>**Max Profit:** Strike width minus net debit paid. | Low / normal IV environments with confirmed bullish trend or support reversal. |
| **Bear Put Debit Spread** | Buy higher-delta (ITM/ATM) put; sell lower-delta (OTM) lower-strike put. | **Max Loss:** Net debit paid.<br>**Max Profit:** Strike width minus net debit paid. | Low / normal IV environments with confirmed bearish breakdown. |
| **Bull Put Credit Spread** | Sell higher-strike put; buy lower-strike protective put. | **Max Profit:** Net credit collected.<br>**Max Loss:** Strike width minus net credit. | High IV environments testing key structural support levels; positive carry. |
| **Bear Call Credit Spread** | Sell lower-strike call; buy higher-strike protective call. | **Max Profit:** Net credit collected.<br>**Max Loss:** Strike width minus net credit. | High IV environments testing structural resistance; positive carry. |
| **Short Iron Condor** | Sell OTM call credit spread and sell OTM put credit spread simultaneously. | **Max Profit:** Combined net credit collected.<br>**Max Loss:** Width of wider wing minus total credit. | High IV, range-bound environments exhibiting high dispersion and mean-reversion. |
| **Long Straddle** | Buy equidistant ATM call and ATM put in identical expiration. | **Max Loss:** Combined net debit paid.<br>**Max Profit:** Theoretically unlimited upside; bounded by strike on downside. | Underpriced volatility or mispriced large catalyst move exceeding market implied move. |
| **Long Strangle** | Buy OTM call and buy OTM put in identical expiration. | **Max Loss:** Combined net debit paid.<br>**Max Profit:** Unlimited upside; downside bounded by put strike minus debit. | Coiling / compression breakouts and low-IV volatility expansion regimes. |
| **Long Calendar Spread**| Sell near-term expiry option; buy deferred-term expiry option at identical strike. | **Max Loss:** Net debit paid (under standard static assumptions).<br>**Max Profit:** Achieved near strike at front-leg expiration. | Inter-temporal term structure mispricing and low-realized volatility consolidation. |

### 1.1 American vs. European Exercise & Path Dependencies

* **American-Style Contracts:** Single-stock equity options typically permit exercise at any point prior to expiration. Short deep-in-the-money options carry substantial early assignment risk, particularly ahead of ex-dividend dates (calls) or when carry costs exceed remaining extrinsic value (puts).
* **European-Style Contracts:** Index options (such as NIFTY, BANKNIFTY, S&P 500) can only be exercised at terminal expiration. This eliminates early assignment risk, making cross-strike spreads and iron condors significantly more predictable during intraday volatility spikes.
* **Payoff Deformation:** Realized P&L paths frequently deviate from theoretical terminal payoff diagrams due to dynamic skew repricing, term-structure shifts, and changing interest rates.

---

## 2. The 13 Institutional Hidden Risks & Live Execution Controls

Options trading exposes capital to non-linear, multi-dimensional risks that cannot be observed through simple delta-gamma metrics alone. The framework establishes specific mechanisms and active operational controls across 13 primary risk vectors:

| Risk Category | Underlying Failure Mechanism | Operational Risk Control Standard |
| :--- | :--- | :--- |
| **1. Volatility Crush** | Implied volatility collapses precipitously following the resolution of binary corporate or macro events (e.g., earnings announcements, regulatory rulings, CPI prints). Long options experience acute vega drawdowns. | Apply event-adjusted implied volatility scenarios. Model post-event implied volatility normalization. Prohibit holding unhedged long vanilla options into binary events without deliberate variance-expansion justification. |
| **2. Gamma Acceleration** | As expiration nears, ATM option gamma increases hyperbolically ($\Gamma \propto \frac{1}{\sigma \sqrt{t}}$). Local delta changes violently with minor underlying movements, creating massive P&L volatility. | Implement strict portfolio gamma exposure caps. Enforce mandatory expiration roll protocols (e.g., closing or rolling positions prior to final expiration week). Restrict front-week net short gamma exposure. |
| **3. Skew Migration** | During market selloffs, out-of-the-money put volatility expands substantially faster than at-the-money volatility. Bearish skew steepens, causing short put spreads to mark at severe paper losses even if the spot price remains above the short strike. | Conduct strike-specific skew stress tests. Reprice portfolio positions across non-parallel surface shifts. Model asymmetric wing repricing rather than assuming static ATM vega sensitivity. |
| **4. Term Inversion** | The volatility curve inverts from normal contango into acute backwardation during sudden stress events. Front-month options spike relative to back-month options, causing calendar spreads and diagonal structures to suffer severe losses. | Track synthetic constant-maturity forward-variance metrics ($\sigma^2_{\text{fwd}}$). Place dynamic maturity-allocation limits on calendar spreads. Stress-test term curve inversions across all calendar books. |
| **5. Volatility-of-Volatility** | The volatility surface moves non-linearly and independently of underlying spot movement. Implied volatility distributions exhibit heavy tails and jump dynamics. | Incorporate second-order cross-Greek limits (Vanna and Volga/Vomma). Conduct historical volatility-of-volatility regime stress tests. Model multi-sigma implied volatility expansion shocks. |
| **6. Gap Risk** | The underlying asset experiences discontinuous overnight or weekend price gaps that jump past protective wing strikes, bypassing stop-loss orders. | Execute discrete jump-diffusion stress simulations. Recognize that defined-risk spreads limit theoretical terminal loss but do not eliminate catastrophic gap slippage or intra-period liquidity lockouts. |
| **7. Liquidity Collapse** | During acute market panics, market makers pull quotes, causing bid-ask spreads to widen exponentially and market depth to evaporate. Closing or hedging positions incurs massive transaction friction. | Implement executable bid-ask spread filters. Model positions at executable bid/ask depth rather than theoretical mark-to-mid. Enforce strict minimum average daily volume (ADV) and open interest (OI) screening filters. |
| **8. Multi-Leg Slippage** | Executing complex multi-leg structures (iron condors, calendars) across individual legs results in execution drag, partial fills, and leg-out market exposure. | Enforce atomic multi-leg execution orders via exchange complex order books (COBs). Incorporate realistic bid-ask half-spread penalties in backtesting frameworks. |
| **9. Margin Expansion** | Clearinghouses and prime brokers dynamically adjust margin requirements (e.g., SPAN margin, extreme loss margins) during heightened volatility, triggering forced position liquidations. | Maintain a minimum 30–40% cash and cash-equivalent margin buffer above exchange requirements. Conduct stressed margin requirement simulations under multi-sigma market shocks. |
| **10. Assignment & Settlement** | Short in-the-money options face sudden physical delivery obligations or early exercise. Short put holders can be assigned underlying shares overnight, incurring massive unintended equity exposure and financing costs. | Closely monitor extrinsic value thresholds on short options. Track corporate action ex-dates. Enforce mandatory exit protocols for deep ITM short legs prior to final settlement. |
| **11. Expiry Pin Risk** | The underlying asset closes precisely at or adjacent to a short strike at expiration. The trader cannot determine whether the counterparty will exercise, creating uncertain naked directional exposure over the weekend. | Close or roll any short option position trading within $\pm 0.5 \times \text{ATR}$ of the underlying spot price prior to the final expiration cutoff window. Never hold short ATM strikes into settlement. |
| **12. Correlation Shock** | During broad market panics, cross-asset correlations snap toward 1.0. Diversified single-stock option credit spreads experience simultaneous adverse drawdowns, overwhelming portfolio capital. | Run portfolio-level joint correlation shock models. Evaluate factor-based equity beta exposure. Enforce hard limits on total aggregate portfolio directional delta and gross vega. |
| **13. Transaction Drag & Taxes** | High rebalancing turnover, exchange fees, brokerage commissions, and statutory turnover taxes continuously erode theoretical strategy expectancy. | Report all quantitative backtest results net of all direct transaction charges, stamp duties, GST, and turnover taxes. Reject strategies whose theoretical alpha fails to cover transaction friction by at least $3\times$. |

---

## 3. Indian Derivatives Market Microstructure & Execution Checklist

Deploying institutional options strategies in the Indian derivatives market (NSE) requires adherence to specific exchange mechanics, regulatory structures, and contract conventions:

### 3.1 Market Architecture & Expiry Dynamics
* **Weekly vs. Monthly Expiry Cycles:** Weekly options contracts on benchmark indices (NIFTY, BANKNIFTY) exhibit concentrated gamma and aggressive time decay. Monthly contracts provide deeper liquidity across wing strikes. Desks must adjust delta screening bands depending on whether trades are staged in weekly or monthly series.
* **Exchange Holiday Calendars:** Indian exchange holidays frequently shift weekly expiration days from Thursday to Wednesday. Quantitative calendar systems must synchronize with exchange holiday circulars to avoid expiry mismatch in calendar and diagonal spreads.

### 3.2 Contract Sizing & Corporate Actions
* **Periodic Lot Size Revisions:** SEBI and the NSE periodically revise derivatives lot sizes to maintain contract values within designated rupee bands. Desks must monitor scheduled lot-size transitions to prevent position sizing mismatches.
* **Corporate Action Adjustments:** Dividends, stock splits, bonus issues, and rights offerings alter strike prices and contract multipliers. Single-stock options require tracking ex-dates to prevent unexpected early exercise or dividend arbitrage assignment.

### 3.3 Transaction Taxation & Statutory Friction
* **Securities Transaction Tax (STT):** Indian derivatives trading incurs statutory STT charges. Desks must account for STT on option sales and exercise values, which materially affects deep-in-the-money long options upon physical settlement.
* **Statutory Charges Spectrum:** Full cost models must incorporate Exchange Turnover Charges, SEBI Regulatory Fees, Integrated Goods & Services Tax (GST at 18% on brokerage and transaction fees), and State Stamp Duty.

### 3.4 Physical Delivery Obligations
* **Mandatory Physical Settlement:** All stock derivatives on the NSE are subject to mandatory physical delivery upon expiration. Expiring in-the-money short call positions obligate the seller to deliver physical shares; expiring in-the-money short put positions require funding the full purchase price of underlying shares.
* **Operational Control:** Desks must square off all expiring single-stock options prior to the physical settlement delivery window unless physical share delivery or acquisition is explicitly intended and fully funded.

### 3.5 Microstructure Liquidity & Margin Protocols
* **Execution Depth & Pin Risk:** Index options maintain high liquidity near ATM strikes, but liquidity deteriorates rapidly beyond the 10-delta wing strikes. Desks must measure real-time market depth and calculate market impact before placing block orders.
* **SPAN & Exposure Margin Buffer:** Indian exchanges enforce Standard Portfolio Analysis of Risk (SPAN) and Exposure Margins calculated on a real-time portfolio basis. Intraday volatility spikes trigger instantaneous margin calls. Desks must maintain adequate margin headroom to absorb intraday peak margin expansion without risking automated broker liquidations.
