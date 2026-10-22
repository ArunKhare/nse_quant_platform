# Trading Universe Roadmap

This document defines the intended instrument universe and expansion path for
the NSE Quant Decision Platform.

The platform will support three primary trading families:

1. NIFTY index options
2. Cash stocks
3. Stock options

Each family will support intraday, swing, and positional horizons over time.
Other indices will initially be used for market context, beta, sector strength,
and research—not as additional trading universes.

Live trading remains disabled. All strategies must operate in paper mode and
inherit the persistent kill switch, dry-run behavior, data-quality checks,
liquidity checks, and risk controls.

## Scope summary

| Instrument family | Priority | Horizons | Initial role |
|---|---:|---|---|
| NIFTY index options | P0 | Intraday, swing, positional | Primary options strategy universe |
| Cash stocks | P1 | Intraday, swing, positional | Directional equity trading |
| Stock options | P1 | Intraday, swing, positional | Defined-risk stock-option strategies |
| BANKNIFTY and sector indices | P2 | Context only | Market regime, beta, sector strength |
| Other index options | P3 | Later | Add only after core tracks are stable |

## Guiding principles

- Start with NIFTY options because the platform already has a working NIFTY
  paper-decision core.
- Add cash stocks and stock options as separate strategy families.
- Use NIFTY, BANKNIFTY, and sector indices as shared market-context layers.
- Add one strategy, one instrument family, or one horizon at a time.
- Keep every new track paper-only until it has enough evidence and risk controls.
- Do not allow a new strategy or asset class to weaken existing safety controls.

## NIFTY index options

NIFTY is the first complete options-trading universe.

### Horizons

| Horizon | Holding period | Main focus |
|---|---|---|
| Intraday | Same day | Opening range, VWAP, OI shifts, IV behavior, expiry effects |
| Swing | 2–5 trading days | Trend and IV context, event avoidance, defined-risk structures |
| Positional | 1–4 weeks | DTE selection, wider wings, overnight gap risk, roll rules |

### Initial NIFTY strategies

Add strategies one at a time in paper mode:

1. `iron_condor_monitor` — existing short-volatility range strategy.
2. `nifty_bull_call_spread` — directional bullish strategy.
3. `nifty_bear_put_spread` — directional bearish strategy.
4. `nifty_iron_fly` — optional range strategy.
5. `nifty_calendar_spread` — optional volatility term-structure strategy.

Each strategy must have its own:

- Strategy profile.
- Underlying allowlist.
- Regime policy.
- Risk limits.
- Exit rules.
- DTE and expiry rules.
- Performance tracking.

## Cash stocks

Cash stocks are a separate directional-equity track.

### Horizons

| Horizon | Holding period | Main focus |
|---|---|---|
| Intraday | Same day | Opening range, VWAP, relative volume, trend continuation |
| Swing | 2–10 trading days | Breakout, trend, relative strength, earnings avoidance |
| Positional | Weeks to months | Trend, fundamentals, sector strength, beta-aware sizing |

### Initial stock universe

Start with liquid NSE large caps:

- RELIANCE
- HDFCBANK
- ICICIBANK
- INFY
- TCS
- SBIN
- AXISBANK
- TATAMOTORS
- MARUTI
- SUNPHARMA

The active trading watchlist should remain smaller than the research universe.
Begin with 5–10 highly liquid stocks.

### Initial cash-stock strategy

Use a simple, testable trend-following swing strategy:

- Entry: close above SMA50 and SMA200.
- Breakout: close above the 20-day high.
- Volume: relative volume above a configured threshold.
- Stop: 2 × ATR14 below entry.
- Target: 2R to 3R, or trailing exit.
- Time stop: exit after a defined number of trading days.
- Event filter: no new entry immediately before earnings or other high-impact
  events.

### Stock-specific requirements

Cash stocks require features that do not apply to index options:

- Corporate-action-adjusted historical prices.
- Earnings and results calendar.
- Dividend, split, bonus, and buyback awareness.
- Delivery-volume research.
- Sector and benchmark mapping.
- Beta versus NIFTY and the relevant sector index.
- Stock-specific liquidity and impact-cost checks.

## Stock options

Stock options are the second options family, after NIFTY options.

### Initial stock-option universe

Begin with liquid NIFTY stocks that have active NFO option chains:

- RELIANCE
- HDFCBANK
- ICICIBANK
- INFY
- TCS
- SBIN
- AXISBANK
- TATAMOTORS
- MARUTI
- SUNPHARMA

### Horizons

| Horizon | Holding period | Main focus |
|---|---|---|
| Intraday | Same day | Stock momentum, opening range, event avoidance |
| Swing | 2–10 trading days | Trend, relative strength, earnings and event risk |
| Positional | Weeks | Trend, beta, sector strength, defined-risk structures |

### Initial stock-option strategies

Use defined-risk structures first:

- Bull call spread.
- Bear put spread.
- Iron condor.
- Iron fly.
- Protective put or collar, later.

Avoid naked short options and deep OTM wings initially. Stock options can have
wider spreads, lower depth, and sharper event-driven gaps than NIFTY options.

### Stock wings

“Stock wings” refers to the long protective options in defined-risk structures
such as iron condors, iron flies, and spreads.

For stock-option wings:

- Use wider wings than NIFTY initially.
- Prefer liquid ATM and near-ATM strikes.
- Avoid deep OTM wings with poor OI or wide bid-ask spreads.
- Check event risk before entry.
- Reduce size around earnings, results, and high-volatility regimes.
- Avoid holding short-volatility structures through binary events.

A defined-risk structure does not guarantee good execution. Liquidity, spread,
and gap risk remain important.

## Relationship between cash stocks and stock options

Cash stocks and stock options should share market data and research context, but
remain separate strategy families.

| Cash-stock signal | Possible stock-option expression |
|---|---|
| Bullish breakout | Bull call spread |
| Bearish breakdown | Bear put spread |
| Range-bound outlook | Iron condor or iron fly |
| High IV before earnings | Avoid new short-volatility structures |
| Post-event IV crush | Consider defined-risk premium-selling strategies |
| Strong uptrend with high beta | Reduce option position size |
| Stock-specific event risk | Block new entries or use protective structures |

Cash-stock technicals can generate the directional view. Stock options can
express that view with defined risk.

## NIFTY as market context

NIFTY remains the central market-regime benchmark for all trading families.

Use NIFTY to assess:

- Broad-market trend.
- Volatility regime.
- IV rank and IV-RV spread.
- Expected move.
- Risk appetite.
- Whether equity and stock-option entries are operating in a supportive
  environment.

For example, a bullish stock breakout should be interpreted differently when
NIFTY is in a strong bull regime versus a high-volatility or bearish regime.

## Other indices: context first

Other indices are primarily for research, beta, breadth, and sector context.

| Index | Main use |
|---|---|
| BANKNIFTY | Banking-sector strength, beta, financial-sector regime |
| NIFTY IT | IT-stock relative strength and sector beta |
| NIFTY ENERGY | Energy-stock context |
| NIFTY AUTO | Auto-stock context |
| NIFTY PHARMA | Pharma-stock context |
| NIFTY 500 | Broad-market breadth and beta benchmark |

### Context features

Persist the following per stock and date:

- `beta_vs_nifty`
- `beta_vs_sector_index`
- `correlation_vs_nifty`
- `correlation_vs_sector_index`
- `relative_strength_vs_nifty`
- `relative_strength_vs_sector`
- `sector_regime`
- `market_breadth`

Beta is calculated from aligned daily returns:

\[
\beta_{stock,B} =
\frac{\operatorname{Cov}(r_{stock}, r_B)}
{\operatorname{Var}(r_B)}
\]

Use a trailing window, typically 126 or 252 trading days. Beta and relative
strength should initially be observational features, not hard entry gates.

## Configuration model

Keep tradable instruments, context instruments, and future instruments separate.

```yaml
trading_universe:
  nifty_options:
    enabled: true
    horizons: [intraday, swing, positional]
    strategies:
      - iron_condor_monitor

  cash_stocks:
    enabled: false
    horizons: [intraday, swing, positional]
    watchlist:
      - RELIANCE
      - HDFCBANK
      - ICICIBANK
      - INFY
      - TCS
      - SBIN
      - AXISBANK
      - TATAMOTORS
      - MARUTI
      - SUNPHARMA

  stock_options:
    enabled: false
    horizons: [intraday, swing, positional]
    watchlist:
      - RELIANCE
      - HDFCBANK
      - ICICIBANK
      - INFY
      - TCS

  context_indices:
    enabled: true
    indices:
      - NIFTY
      - BANKNIFTY
      - NIFTY_IT
      - NIFTY_ENERGY
      - NIFTY_AUTO
      - NIFTY_PHARMA
      - NIFTY_500

  index_options:
    enabled: false
    tradable_indices: []
```

## Expansion phases

### Phase 1 — NIFTY options core

1. Stabilize the NIFTY paper decision loop.
2. Complete multi-timeframe evidence.
3. Add event-risk evidence.
4. Add technical-indicator, volume-flow, and option-positioning plugins.
5. Add one additional NIFTY strategy at a time.
6. Build sufficient complete-day history for research and backtesting.

### Phase 2 — Cash stocks

1. Add equity instruments and an equity watchlist.
2. Capture equity candles.
3. Handle corporate actions and adjusted historical prices.
4. Add stock technical features, beta, and relative strength.
5. Add an equity event calendar.
6. Launch one cash-stock swing strategy in paper mode.

### Phase 3 — Stock options

1. Add stock-option chains and stock-specific liquidity thresholds.
2. Add stock-specific event-risk rules.
3. Add defined-risk stock-option strategies.
4. Launch one stock-option strategy in paper mode.
5. Track execution quality separately from NIFTY options.

### Phase 4 — Multi-horizon strategies

1. Add explicit intraday, swing, and positional strategy profiles.
2. Add DTE selection, entry windows, holding-period limits, and force-exit
   rules.
3. Add overnight gap and event-risk controls for swing and positional trades.
4. Backtest each horizon separately.

### Phase 5 — Broader index context

1. Add BANKNIFTY and sector indices as context benchmarks.
2. Compute beta, correlation, relative strength, and breadth.
3. Use context to qualify NIFTY, cash-stock, and stock-option strategies.
4. Consider additional index options only after the core tracks are stable.

## Shared platform components

These components should be shared across all instrument families:

| Component | Purpose |
|---|---|
| Kite instrument resolution | Resolve index, equity, and option instruments |
| Candle storage | Store 1m, 15m, 60m, and daily OHLCV data |
| Feature engine | Compute returns, ATR, VWAP, trend, volume, and regime features |
| Evidence plugins | Persist observational research context |
| Decision loop | Run gates, proposals, risk checks, and paper execution |
| DuckDB persistence | Store decisions, positions, evidence, and market data |
| Parquet warehouse | Export research-ready historical data |
| EOD maintenance | Build daily research artifacts and review open positions |
| Kill switch | Halt all strategy activity |
| Risk engine | Enforce strategy and portfolio-level limits |

## Safety boundary

Every instrument family must inherit the same non-negotiable controls:

- Persistent kill switch.
- Paper-only mode.
- Dry-run behavior.
- Market-hours enforcement.
- Data-quality gates.
- Liquidity gates.
- Per-strategy risk limits.
- Portfolio-level exposure limits.
- EOD review and warehouse exports.

A new strategy must never bypass these controls.

## Strategy promotion rules

A strategy, instrument family, or horizon should move from observational to
tradable only after:

1. It has a dedicated paper-only configuration.
2. It has enough complete trade cycles.
3. Its data quality and liquidity are reliable.
4. Its risk limits and exit rules are tested.
5. Its performance is evaluated across market regimes.
6. Its drawdown, slippage, and event risk are understood.
7. It does not destabilize existing strategies.

## Immediate priority

The immediate priority is:

```text
NIFTY options core
  → cash stocks
  → stock options
  → multi-horizon strategies
  → broader index context
  → additional index options only if evidence supports them
```

This keeps the platform focused while creating a clear path from the current
NIFTY iron-condor paper system to a multi-asset, multi-horizon decision platform.