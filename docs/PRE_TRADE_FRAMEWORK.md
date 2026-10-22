# Pre-Trade Framework: Stocks & Options

This document defines the platform’s pre-trade decision hierarchy for NIFTY
options today and a future equity/stock track.

The framework separates:

1. Non-negotiable safety and risk controls.
2. Market context.
3. Trade structure and liquidity.
4. Options and positioning confirmation.
5. Momentum and execution triggers.
6. Post-entry management.

A concept should become a **hard gate** only after it is measurable, stable, and
supported by paper-trade or backtest evidence. Until then, it should be persisted
as **observational evidence**.

## Guiding principle

The platform must not confuse a useful observation with a proven edge.

- **Hard gate:** Must pass before a proposal can proceed.
- **Observational evidence:** Recorded with every decision for research.
- **Manual journal field:** Human context that cannot yet be reliably automated.

Live trading remains disabled. Paper mode, dry-run behavior, and the persistent
kill switch always take precedence over any confluence score or strategy signal.

## Decision hierarchy

| Priority | Layer | Question | Platform role |
|---:|---|---|---|
| 1 | Safety | Is trading permitted and data reliable? | Hard gate |
| 2 | Risk | Is the trade size and loss exposure controlled? | Hard gate |
| 3 | Market context | Is the broader environment suitable? | Gate or evidence |
| 4 | Structure | Is there a real, tradeable market structure? | Evidence first |
| 5 | Liquidity | Can the trade be entered and exited cleanly? | Hard gate |
| 6 | Options positioning | Does OI/IV positioning support the thesis? | Evidence first |
| 7 | Momentum | Is there a timely entry trigger? | Evidence first |
| 8 | Execution | Is the entry window and risk-reward acceptable? | Gate or evidence |
| 9 | Psychology | Am I following the plan? | Manual journal |

## Current mandatory gates

For the existing `iron_condor_monitor` paper strategy, these checks remain
mandatory:

- Persistent kill switch is inactive.
- NSE market is open.
- Market data is not stale and passes data-quality checks.
- Feature availability is sufficient under the configured policy.
- IV history satisfies the configured minimum, or cold-start is explicitly allowed.
- IV rank and IV-RV spread meet configured thresholds.
- Expected move is available and within the configured buffer.
- All required CE and PE legs are present.
- Every required option leg passes OI and bid-ask spread liquidity checks.
- Net credit meets the strategy’s minimum credit.
- Market regime is allowed by strategy eligibility.
- Risk limits approve the proposal.
- Safety remains in paper/dry-run mode.

These controls must not be bypassed by a confluence score.

## Market context

Market context determines whether the environment is suitable for a strategy.

### Index trend

Use NIFTY and, where relevant, BANKNIFTY or another related index.

Current platform inputs:

- Daily close versus SMA50.
- ATR14-normalized distance from SMA50.
- Trend classification: `BULL`, `BEAR`, `RANGE`, or `UNKNOWN`.

Future observational fields:

- Higher-timeframe structure: daily and 1-hour.
- Higher-high/higher-low versus lower-high/lower-low sequence.
- Break of structure (BOS).
- Change of character (CHoCH).
- Trendline or channel state.
- Opening range.
- Gap classification: gap up, gap down, breakaway, exhaustion.

### Volatility regime

Use realized volatility and implied volatility together.

Current platform inputs:

- Realized volatility.
- RV percentile.
- IV rank or IV percentile.
- IV-RV spread.
- ATM IV.
- Expected move.

Future observational fields:

- VIX or India VIX regime.
- IV term-structure state.
- IV crush risk.
- Volatility expansion or contraction.

### Global and event context

These should be observational initially:

- GIFT Nifty.
- US market close and overnight movement.
- Dollar index (DXY).
- US bond yields.
- Crude oil.
- Major scheduled events: RBI, Fed, Budget, earnings, results.
- Expiry-day effects.

Event context should eventually support a hard **event-risk blackout** for new
entries, but it should not automatically close existing positions without a
defined rule.

## Price action and structure

Price action helps distinguish a genuine move from noise.

### Current inputs

The platform already captures and derives:

- 1-minute OHLCV candles.
- 15-minute and 60-minute completed-bucket context.
- One-bar higher-timeframe returns.
- ATR at 1m, 15m, and 60m horizons.
- Range position within a candle.
- VWAP and VWAP distance.
- Volume z-score.

### Future structure features

Add these as observational evidence first:

- Swing highs and swing lows.
- Market structure: HH-HL, LH-LL, range.
- BOS and CHoCH.
- Support and resistance zones.
- Trendlines and channels.
- Fair value gaps (FVG).
- Order blocks.
- Mitigation and breaker blocks.
- Liquidity sweeps.
- Equal highs and equal lows.
- Opening-range breakout or failure.
- Gap analysis.

These labels must be computed using only completed candles to avoid lookahead
bias.

## Volume and order flow

Volume confirms whether a price move has participation.

### Current inputs

- Option-leg volume.
- Spot volume.
- 30-period volume z-score.
- Bid and ask quotes.

### Future volume features

- Relative volume (RVOL).
- Volume delta.
- Buying versus selling imbalance.
- Absorption.
- Volume climax.
- Volume profile.
- Point of control (POC).
- Value-area high and low.
- Delivery volume for cash-equity research.

Volume should usually confirm structure and momentum, not replace them.

## Options data

Options data is especially important for index trading.

### Current inputs

- Option-chain snapshots.
- ATM IV.
- IV rank and IV percentile.
- IV-RV spread.
- Open interest.
- Option volume.
- Bid-ask spread.
- Greeks where available.
- Expected move.
- Max pain-related research.

### Future OI analytics

Persist and classify:

- Change in OI.
- OI build-up.
- Long build-up.
- Short build-up.
- Long unwinding.
- Short covering.
- OI shift at key strikes.
- Option-chain resistance and support.
- Max pain and its change.
- Call traps and put traps.
- Gamma exposure and dealer-positioning estimates.

A simple initial OI classification can be:

| Price change | OI change | Initial interpretation |
|---|---|---|
| Up | Up | Long build-up |
| Down | Up | Short build-up |
| Up | Down | Short covering |
| Down | Down | Long unwinding |

These labels are heuristics, not certainties. They should be stored with the
underlying price change, OI change, expiry, and strike so they can be validated
against outcomes.

## Momentum and mean reversion

Momentum helps time an entry; mean-reversion context helps avoid chasing
extended moves.

### Future indicators

Add these as observational evidence:

- RSI.
- RSI divergence.
- MACD.
- Stochastic RSI.
- ADX.
- EMA 9, EMA 20, EMA 50, and EMA 200 alignment.
- Short-term momentum.
- Mean-reversion distance from VWAP or EMA.
- ATR-normalized move.

### Example confluence

A long setup may have:

- Price above EMA20 and EMA50.
- EMA20 above EMA50.
- RSI above 50 but not extremely overbought.
- MACD histogram expanding.
- Price holding above VWAP.
- Volume above relative average.
- NIFTY structure not strongly bearish.

A short setup uses the inverse conditions.

## Execution confirmation

Execution confirmation separates a theoretically valid idea from a practically
tradeable one.

### Current execution checks

- Market is open.
- Required option legs exist.
- OI meets the minimum threshold.
- Bid-ask spread is within the maximum allowed percentage.
- Net credit meets the minimum requirement.
- Risk limits approve the proposal.

### Future execution checks

- Entry window is active.
- Bid-ask spread is stable across recent observations.
- Quoted depth is sufficient for intended size.
- Expected slippage is acceptable.
- Risk-reward is at least 1:2.
- Retest or pullback confirmation is present, if required by the setup.
- No conflicting higher-timeframe signal.

For index options, avoid illiquid strikes and avoid entering during the first
few minutes unless the strategy explicitly models opening volatility.

## Intraday timing filters

Timing filters reduce exposure to low-quality periods.

Initial observational windows:

- `09:20–10:30`: Trend or opening-range continuation setups.
- `11:30–13:30`: Often lower-quality, choppy session; use cautiously.
- `13:30–14:30`: Potential expansion or trend continuation.
- `14:30–15:15`: Short-covering, reversal, or expiry-related moves.

These are hypotheses, not fixed rules. The platform should record the time
bucket with every decision and evaluate performance by session window.

Future hard filters may include:

- No new entries in the first 3–5 minutes.
- No new entries during a configured low-quality lunch window.
- No new entries close to expiry for strategies vulnerable to gamma.
- No new entries during event blackouts.

## Risk management

Risk management is the most important layer and must remain independent of
signal quality.

### Current controls

- Maximum lots per order.
- Maximum open positions.
- Maximum daily loss.
- Maximum notional exposure.
- Option-specific portfolio limits.
- Regime-based scaling of risk limits.
- Paper-only execution and persistent kill switch.

### Future controls

- Maximum risk per trade as a percentage of capital.
- Minimum risk-reward ratio.
- Maximum portfolio heat.
- Maximum correlation exposure.
- Maximum sector exposure.
- Maximum consecutive-loss cooldown.
- Maximum trades per day.
- Trailing-stop rules.
- Partial-profit rules.
- Event-risk position limits.

A basic per-trade sizing formula is:

\[
\text{quantity} =
\left\lfloor
\frac{\text{capital} \times \text{risk per trade}}
{\text{entry price} - \text{stop price}}
\right\rfloor
\]

For option strategies, risk should also consider premium at risk, wing width,
expected move, gamma near expiry, and portfolio Greeks.

## Psychological filters

Psychological filters should initially be recorded as manual journal fields
attached to a paper decision:

- `planned_trade`: yes/no.
- `setup_followed`: yes/no.
- `emotional_state`: calm, anxious, confident, frustrated.
- `fomo_risk`: low, medium, high.
- `revenge_trade_risk`: low, medium, high.
- `would_take_manually`: yes/no.
- `notes`: free-form context.

These fields create labeled data for later review. They should never
automatically override safety controls, but repeated poor psychological states
can trigger a review alert.

## Confluence score

Use a transparent score rather than a black-box decision.

| Component | Weight | Example requirement |
|---|---:|---|
| Market context | 20 | Allowed NIFTY regime; suitable IV/RV context |
| Structure | 20 | Higher-timeframe structure supports direction |
| Volume participation | 15 | RVOL and volume z-score confirm the move |
| Options positioning | 20 | OI change, PCR, IV, and expected move support thesis |
| Momentum trigger | 15 | RSI, MACD, EMA, or ADX confirms timing |
| Execution quality | 10 | Liquidity, timing, spread, and RR are acceptable |

Suggested interpretation:

| Score | Action |
|---:|---|
| 80–100 | Eligible for paper proposal, subject to hard gates |
| 60–79 | Observe and persist, but do not trade |
| Below 60 | No trade |

The score must never override:

- Persistent kill switch.
- Paper/dry-run safety mode.
- Data-quality failure.
- Liquidity failure.
- Risk-limit rejection.
- Event-risk blackout.

## Minimal pre-entry checklist

Before any paper entry, require:

1. Kill switch inactive.
2. Market open and data fresh.
3. Strategy enabled and underlying allowed.
4. Market regime suitable.
5. Volatility and IV context suitable.
6. Structure supports the intended direction.
7. Volume or participation confirms the move.
8. Options/OI context supports the thesis, for index trades.
9. Liquidity is sufficient on every required leg.
10. Entry is within the allowed time window.
11. Risk-reward is at least 1:2.
12. Position size and portfolio exposure are within limits.
13. No unresolved event-risk conflict.
14. The trader would take the setup manually.

If two or more important confluence components are missing, the platform should
record the setup as `observe_only`, not generate a proposal.

## Implementation roadmap

### Phase 1: Persist the framework

Add a `pre_trade_context` payload to each decision cycle:

- NIFTY regime.
- IV regime.
- RV regime.
- Trend and ATR context.
- VWAP distance.
- Volume z-score.
- OI snapshot and OI change.
- PCR.
- Expected move.
- Liquidity checks.
- Entry-window status.
- Event-calendar status.
- Confluence score.

### Phase 2: Add observational plugins

Implement plugins for:

- Technical indicators: RSI, MACD, ADX, EMA alignment.
- Volume analytics: RVOL and volume delta.
- OI analytics: OI change and build-up classification.
- Structure analytics: swing points, BOS/CHoCH, opening range.
- Market context: GIFT Nifty, global cues, event calendar.

Plugin failures must be caught and persisted as unavailable evidence. They must
never stop the paper loop or alter safety behavior.

### Phase 3: Add hard controls

Promote only well-tested rules to hard gates:

- Event blackout.
- Entry-window restriction.
- Minimum risk-reward.
- Maximum daily loss.
- Maximum consecutive losses.
- Expiry-day and DTE restrictions for positional strategies.
- Liquidity and depth thresholds.

### Phase 4: Validate with research

For every potential gate, measure:

- Win rate with and without the filter.
- Average P&L.
- Maximum drawdown.
- Trade count.
- Profit factor.
- Slippage and liquidity impact.
- Performance across market regimes.

A filter should be promoted only if it improves risk-adjusted outcomes without
reducing the sample below a usable size.

## Stock-track extension

For a future equity strategy, reuse the same hierarchy but replace option-specific
checks with stock-specific checks:

| Layer | Stock equivalent |
|---|---|
| Market context | NIFTY, sector index, market breadth |
| Structure | Daily/1H trend, swing structure, breakout |
| Volume | RVOL, delivery volume, volume delta |
| Options data | Not required for cash-stock trades |
| Momentum | RSI, MACD, EMA alignment, ADX |
| Execution | Spread, depth, average volume, impact estimate |
| Risk | Position size, stop distance, sector and correlation exposure |
| Events | Earnings, results, board meetings, corporate actions |

For stocks, calculate beta and relative strength against NIFTY and the relevant
sector index. These should initially be observational features, not entry gates.

## Status

- Current platform: NIFTY iron-condor paper-only.
- Current hard controls: safety, data quality, IV/RV, expected move, liquidity,
  eligibility, risk, and kill switch.
- Current research direction: persist confluence evidence before promoting it
  into strategy decisions.
- Live trading: disabled.