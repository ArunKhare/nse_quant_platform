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

## Promotion rule

A future configuration block may be moved into `config/settings.yaml` only when:

1. Its settings model exists.
2. Its plugin or service is implemented.
3. Its persistence is implemented.
4. Its tests pass.
5. Its decision-loop integration is complete.
6. It is safe to enable in paper mode.
7. It does not weaken the persistent kill switch, paper mode, or risk controls.