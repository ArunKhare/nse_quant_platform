# Future Implementation Configuration

This document contains configuration designs for features that are planned but
not yet implemented.

These blocks must not be copied into `config/settings.yaml` until their
corresponding settings models, plugins, persistence, tests, and decision-loop
integrations are implemented.

Keeping future configuration separate prevents `enabled: true` from implying
that a feature is active.

## Future evidence plugins

```yaml
evidence:
  enabled: true
  plugins:
    multi_timeframe:
      enabled: true
      timeframes: [1m, 15m, 60m]
      history_limit: 6000

    event_risk:
      enabled: false
      block_new_entries: false

    technical_indicators:
      enabled: false
      timeframes: [1m, 15m, 60m]

    volume_flow:
      enabled: false

    option_positioning:
      enabled: false

    institutional_regime:
      enabled: false
      iv_history_limit: 250
      high_iv_rank_threshold: 70.0
      term_structure_tolerance: 0.002
      skew_threshold: 0.03
      require_complete_regime: false

    market_structure:
      enabled: false
      timeframes: [15m, 60m, day]

    market_context:
      enabled: false

    execution_quality:
      enabled: false
```

### Event risk

Purpose:

- Detect scheduled high-impact events.
- Map events to affected instruments.
- Optionally block new entries during configured blackout windows.

Required implementation:

- `EventRiskSettings`
- `EventRiskPlugin`
- `market_events` table
- Event ingestion service
- Event-to-instrument mapping
- Decision-loop integration
- Tests
```yaml
event_risk:
  enabled: true
  block_new_entries: false
  blackout_minutes_before: 30
  blackout_minutes_after: 30
```
### Technical indicators

Purpose:

- Add momentum, trend-strength, and mean-reversion context.

Planned metrics:

- RSI(14)
- MACD
- Stochastic RSI
- ADX(14)
- EMA 9, 20, 50, 200
- EMA alignment
- ATR-normalized momentum
- RSI divergence

Required implementation:

- `TechnicalIndicatorSettings`
- `TechnicalIndicatorsPlugin`
- Indicator calculations from completed candles
- Decision-loop integration
- Tests
```yaml
technical_indicators:
  enabled: false
  timeframes: [1m, 15m, 60m]
  history_limit: 6000
  rsi_period: 14
  ema_periods: [9, 20, 50, 200]
```
### Volume flow

Purpose:

- Determine whether price movement has participation.

Planned metrics:

- Relative volume (RVOL)
- Volume z-score
- Volume trend
- Volume delta
- Buying/selling imbalance
- Absorption
- Volume climax

Required implementation:

- `VolumeFlowSettings`
- `VolumeFlowPlugin`
- Candle-volume analytics
- Optional tick-side delta ingestion
- Decision-loop integration
- Tests
```yaml
volume_flow:
  enabled: false
  timeframes: [1m, 15m, 60m]
  history_limit: 6000
  baseline_periods: 30
```
### Option positioning

Purpose:

- Synthesize option-chain positioning for NIFTY and future stock options.

Planned metrics:

- PCR and PCR change
- Call/put OI and OI change
- OI build-up classification
- Max pain and max-pain change
- ATM IV change
- Expected-move change
- IV-crush risk
- Call/put trap warnings

Required implementation:

- `OptionPositioningSettings`
- `OptionPositioningPlugin`
- OI history storage
- PCR and max-pain calculations
- Decision-loop integration
- Tests

### Institutional regime

Purpose:

- Produce a point-in-time institutional market-regime label.
- Combine IV state, IV term structure, skew state, and completed price action.
- Support the manual’s 108-regime taxonomy without introducing look-ahead bias.
- Initially provide observational evidence; do not enforce strategy eligibility until validated.

Regime dimensions:

| Dimension | Point-in-time inputs | Planned states |
|---|---|---|
| IV state | ATM IV, historical IV rank/percentile | `HIGH_IV`, `NORMAL_IV` |
| Term structure | Near-term and deferred-expiry IV | `CONTANGO`, `FLAT`, `BACKWARDATION` |
| Skew state | Put/call IV skew from current chain | `NORMAL_SKEW`, `HIGH_PUT_SKEW`, etc. |
| Price action | Completed 1m, 15m, 60m, and daily candles | Six price-action states |

Example regime:

```text
HIGH_IV_CONTANGO_NORMAL_SKEW_RANGE_UPPER
```

Required implementation:

- `InstitutionalRegimeSettings`
- `InstitutionalRegimePlugin`
- Point-in-time IV-history query
- Term-structure calculation from timestamped option-chain snapshots
- Skew calculation from timestamped option-chain snapshots
- Completed-candle-only price-action classification
- Regime-evidence persistence
- Decision-loop integration
- Tests

Look-ahead rules:

- Use only observations with `ts <= decision_ts`.
- Use completed candles; never use the forming bar.
- Use only the chain snapshot timestamped at or before the decision.
- Never use future IV, future price action, post-event news, or future market reactions.
- If any required component is unavailable, return an incomplete regime payload rather than fabricating a label.

Initial rollout:

- Implement as observational evidence only.
- Persist the full regime label and component availability.
- Do not use it in `allowed_regimes` or `blocked_regimes` matching until coverage and performance are validated.

### Market structure

Purpose:

- Describe trend, range, breaks, and important price levels.

Planned features:

- Swing highs and lows
- HH-HL, LH-LL, and range classification
- Break of structure (BOS)
- Change of character (CHoCH)
- Opening range
- Gap classification
- Support and resistance
- Trendlines and channels
- Fair value gaps
- Order blocks
- Liquidity sweeps

Required implementation:

- `MarketStructureSettings`
- `MarketStructurePlugin`
- Swing and structure detection
- Completed-candle-only calculations
- Decision-loop integration
- Tests

### Market context

Purpose:

- Add index regime, sector strength, breadth, beta, and global context.

Planned features:

- NIFTY regime
- BANKNIFTY regime
- Sector regimes
- Market breadth
- Stock beta versus NIFTY and sector index
- Relative strength
- GIFT Nifty
- Global cues
- VIX or India VIX regime

Required implementation:

- `MarketContextSettings`
- `MarketContextPlugin`
- Context-index ingestion
- Beta and relative-strength calculations
- Breadth calculations
- Decision-loop integration
- Tests

### Execution quality

Purpose:

- Determine whether an otherwise valid setup is practically tradeable.

Planned checks:

- Bid-ask spread stability
- Quoted depth
- Liquidity score
- Entry-window status
- Risk-reward ratio
- Expected slippage
- Time-to-event risk

Required implementation:

- `ExecutionQualitySettings`
- `ExecutionQualityPlugin`
- Spread and depth tracking
- Entry-window rules
- Risk-reward calculation
- Decision-loop integration
- Tests

## Future trading universe

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

## Required future settings models

These models should be added only when their features are implemented:

- `EventRiskSettings`
- `TechnicalIndicatorSettings`
- `VolumeFlowSettings`
- `OptionPositioningSettings`
- `MarketStructureSettings`
- `MarketContextSettings`
- `ExecutionQualitySettings`
- `CashStockSettings`
- `StockOptionSettings`
- `ContextIndexSettings`
- `IndexOptionSettings`
- `TradingUniverseSettings`

## Evidence plugin rollout

| Sprint | Config change | Outcome |
|---|---|---|
| Current | Enable `multi_timeframe` only | Completed multi-timeframe trend evidence is persisted. |
| Next | Add and enable `event_risk` | Scheduled-event impact and optional new-entry blackout evidence. |
| Then | Add and enable `technical_indicators` | Momentum, trend-strength, and mean-reversion evidence. |
| Then | Add and enable `volume_flow` | Volume participation and flow evidence. |
| Then | Add and enable `option_positioning` | OI, PCR, IV-change, expected-move, and IV-crush evidence. |
| Then | Add `institutional_regime` in observation mode | Point-in-time institutional regime evidence is persisted. |
| Later | Add `market_structure` | Swing, BOS/CHoCH, range, and level evidence. |
| Later | Add `market_context` | Cross-index, breadth, sector, and global-context evidence. |
| Later | Add `execution_quality` | Spread, depth, entry-window, slippage, and risk-reward evidence. |
| Later | Promote `institutional_regime` to eligibility | Only after regime coverage and performance validation. |
| Later | Add `trading_universe.cash_stocks` | Cash-equity research and future strategy track. |
| Later | Add `trading_universe.stock_options` | Stock-option research and future strategy track. |
| Much later | Enable additional index options | Expand index-option universe. |

### Institutional regime promotion checklist

Promote `institutional_regime` from observational evidence to a hard eligibility gate only when:

1. `InstitutionalRegimeSettings` exists.
2. `InstitutionalRegimePlugin` is implemented.
3. Regime evidence is persisted with `as_of`, input timestamps, availability flags, and `classifier_version`.
4. All regime components use point-in-time data.
5. Tests cover complete, incomplete, stale, and missing-input cases.
6. Decision-loop integration is complete.
7. Sufficient complete regime observations exist.
8. Strategy performance has been evaluated across regime labels.
9. Enabling it does not weaken the persistent kill switch, paper mode, liquidity checks, data-quality checks, or risk controls.

## Promotion rule

A future configuration block may be moved into `config/settings.yaml` only when:

1. Its settings model exists.
2. Its plugin or service is implemented.
3. Its persistence is implemented.
4. Its tests pass.
5. Its decision-loop integration is complete.
6. It is safe to enable in paper mode.
7. It does not weaken the persistent kill switch, paper mode, or risk controls.
