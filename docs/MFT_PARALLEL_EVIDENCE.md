# MFT Parallel Evidence

MFT Parallel Evidence is an observational research layer for the paper decision
loop. It captures multi-timeframe market context alongside every decision cycle
without affecting proposal generation, eligibility, risk, or paper execution.

## Purpose

The platform currently captures live NIFTY 1-minute spot candles and option-chain
IV observations. MFT evidence derives higher-timeframe context from completed
1-minute candles so that future research can evaluate whether 15-minute and
60-minute structure improves iron-condor decision quality.

## Non-goals

- MFT evidence does not create trade proposals.
- MFT evidence does not reject a decision.
- MFT evidence does not enable live trading.
- MFT evidence does not use partial higher-timeframe candles as completed candles.
- MFT evidence does not replace daily RV, IV rank, or IV regime research.

## Timeframes

| Timeframe | Source | Availability rule |
|---|---|---|
| 1m | Persisted live 1m candles | Latest completed 1m candle |
| 15m | Derived from completed 1m candles | Closed 15-minute NSE bucket |
| 60m | Derived from completed 1m candles | Closed 60-minute NSE bucket |
| 1d | Previous completed trading day | Current day is never treated as complete intraday |

## Derived OHLCV

For every higher-timeframe bucket:

- `open` is the first 1-minute open.
- `high` is the maximum 1-minute high.
- `low` is the minimum 1-minute low.
- `close` is the last 1-minute close.
- `volume` is the sum of 1-minute volume.

## Evidence fields

For each available timeframe:

- `close`
- `recent_return_20`
- `recent_high_20`
- `recent_low_20`
- `range_position_20`
- `realized_volatility_20`
- `completed_candles`

A timeframe is marked unavailable when there are insufficient completed candles.

## Safety

The plugin runner isolates failures. If a plugin raises an exception, the runner
records an unavailable evidence payload and the paper loop continues normally.

The plugin is enabled through:

```yaml
evidence:
  enabled: true
  plugins:
    multi_timeframe:
      enabled: true
      timeframes: [1m, 15m, 60m]
```
