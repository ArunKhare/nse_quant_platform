# Institutional regime calibration exporter

## Purpose

`scripts/export_institutional_regime_calibration.py` prepares the point-in-time
NIFTY input dataset consumed by
`scripts/run_institutional_regime_calibration.py`. It is an observational
research-data export only. It does not change thresholds, publish a regime,
assert decision eligibility, approve paper trading, or authorize execution.

## Inputs

- `data/nse_quant.duckdb` (read-only by default): completed NIFTY daily bars,
  NIFTY 1-minute bars, and the legacy `option_stream` table.
- An NSE India VIX historical CSV supplied with `--india-vix-csv`. The
  exporter requires `Date` and `Close`; it accepts NSE dates such as
  `28-NOV-2025`. Other columns are retained in the source file and covered by
  its SHA-256 hash.

The exporter does not use `daily_rv_observations.rv` or a precomputed
`daily_rv_NIFTY.csv`: the earlier audit did not establish that those values
were non-annualized realized variance in the units expected by the HAR-RV
calibration. Instead, it derives each session's realized variance from raw
1-minute NIFTY closes as the sum of squared consecutive within-session log
returns. A session is eligible only when it has at least 300 1-minute
observations by default.

## Feature definitions

The output has the exact column order required by the calibration runner:

```text
session, ivp, iv30_minus_iv90, rr25, adx14, plus_di14, minus_di14, er20,
chop14, atr14, atr_percentile, bandwidth_percentile, range_position,
change20, sma20_slope, realized_variance
```

- `ivp`: trailing percentile rank of India VIX Close, over up to 252
  available sessions including the current session, with at least 30
  observations. This is an India VIX proxy, not ATM option IV.
- `iv30_minus_iv90`: 30-calendar-day constant-maturity ATM IV less 90-day
  constant-maturity ATM IV. ATM IV is the mean of call/put IVs within 0.10 delta of +0.50/-0.50.
  The 25-delta wings must be within 0.05 delta of +0.25/-0.25. Maturities
  are interpolated in total-variance space. Extrapolation is prohibited.
- `rr25`: 30-day constant-maturity 25-delta call IV less 25-delta put IV.
  Call/put wing IVs are interpolated in total-variance space. Extrapolation is
  prohibited.
- Daily price-action features use the same `_adx_series` and `_metrics_at`
  calculations as `institutional_regime_price_action_v5`.
- `realized_variance`: sum of squared within-session 1-minute log returns;
  it is not annualized.

The option surface uses the latest `run_id`/timestamp snapshot per India
Standard Time session. If that snapshot cannot provide both term-structure
brackets and both 25-delta wings, the session is omitted; an older snapshot is
not substituted.

## Run

From the repository root:

```powershell
uv run python scripts/export_institutional_regime_calibration.py `
  --india-vix-csv data/external/india_vix_1y.csv
```

Optional arguments:

- `--db-path`: DuckDB path (default `data/nse_quant.duckdb`).
- `--output`: CSV path (default `data/research/nifty_regime_calibration.csv`).
- `--manifest`: JSON manifest path (default `data/research/nifty_regime_sources.json`).
- `--as-of`: exclusive IST date boundary; current IST date is used by default.
- `--end-date`: inclusive last session, always capped before `--as-of`.
- `--min-intraday-observations`: 1-minute bars required per RV session (default 300).
- `--iv-lookback-sessions`: India VIX percentile window (default 252).
- `--iv-min-observations`: minimum India VIX observations for IVP (default 30).

The CSV and manifest are written even when coverage is insufficient, so the
coverage failure is inspectable. The process exits with status 2 unless the
CSV contains at least the configured number of complete sessions. The manifest
records the DuckDB and India VIX CSV SHA-256 hashes, source coverage, feature
definitions, missing-field counts, and readiness status.

## Calibration execution

Only after the exporter reports `READY_FOR_DIAGNOSTIC_CALIBRATION`:

```powershell
uv run python scripts/run_institutional_regime_calibration.py `
  --input data/research/nifty_regime_calibration.csv `
  --output data/research/nifty_regime_calibration_report.md `
  --source-manifest data/research/nifty_regime_sources.json
```

The runner remains diagnostic-only. No threshold promotion or execution
eligibility is implied by a completed report.

## Coverage audit — 2026-11-28

The updated calibration export uses the consolidated India VIX history from
2019-01-01 through 2026-11-27. Its source manifest reports 1,960 source rows
through the requested end date and 1,931 valid trailing-percentile observations.
India VIX coverage is no longer the binding constraint for the 566 daily
candidate sessions in the supplied audit. The VIX source is still a proxy for
option IV, not a replacement for the native constant-maturity option surface.

The supplied DuckDB audit reports:

- 566 valid NIFTY daily bars, yielding 301 daily price-feature sessions.
- 81 sessions with 1-minute bars, of which 80 meet the 300-observation RV floor.
- 29 NIFTY option-stream sessions, of which only 2 have a complete 30D/90D ATM
  term structure and 30D 25-delta risk reversal.
- 1,931 India VIX IVP observations.

The realized-variance source summary now includes a per-session
`session_coverage` record with the observed 1-minute close count, configured
minimum, eligibility flag, and explicit `below_minimum_observations` rejection
reason. This identifies the exact session(s) that fail the RV observation floor
without changing that floor or the realized-variance calculation.

Each option snapshot profile now includes `interpolation_brackets` for 30D ATM,
90D ATM, 30D call-25, and 30D put-25. Each entry reports the target maturity,
status (`exact`, `interpolated`, `missing_lower_bracket`,
`missing_upper_bracket`, or `missing_both_brackets`), and the actual nearest
valid lower/upper DTE and IV observations. These diagnostics use the same
accepted IV/delta observations as the feature calculation; they do not relax
tolerances, change snapshot selection, or permit extrapolation.

The exporter now records option-snapshot rejection reasons separately:
`missing_iv30_atm_bracket`, `missing_iv90_atm_bracket`,
`missing_call25_30d_bracket`, and `missing_put25_30d_bracket`.
It also reports candidate daily sessions without any option snapshot. The
diagnostics use only the latest snapshot per IST session and do not fall back
to an older snapshot, interpolate beyond observed expiries, or synthesize data.

For 423 complete observations, the current feature definitions require at
least 688 valid daily bars, 452 India VIX sessions, 423 sessions with valid
30D/90D term and 25-delta skew, and 423 eligible realized-variance sessions.
The supplied export remains `INSUFFICIENT_SOURCE_COVERAGE`: its complete-row
upper bound is 2, with option surface coverage the tightest current constraint.
The 423-session floor is fixed in the exporter and cannot be lowered through
a CLI option.

The option-surface diagnostics continue to read the legacy `option_stream`
table for this exporter. They do not claim that legacy records are native
Medallion Bronze/Silver evidence, and they do not migrate or backfill any data.

### Option acquisition-path inspection

The active branch contains two materially different Kite acquisition APIs:

- `KiteMarketDataProvider.get_chain_snapshot()` selects one expiry (the nearest
  expiry when none is supplied).
- `KiteMarketDataProvider.get_chain_snapshots()` uses
  `discover_chain_for_horizon()` to select listed expiries through the first
  expiry beyond the configured capture horizon, with a minimum 90-calendar-day
  horizon.
- `kite_stream.py` uses the multi-expiry API and persists each returned expiry
  snapshot. The ordinary `DecisionLoop` path calls the single-expiry API.
- The stream runner previously assigned one timestamp at startup and reused it
  for every polling cycle. Because `option_stream` is keyed by
  `(run_id, ts, instrument_token)`, repeated writes replaced earlier rows for
  the same instrument instead of retaining a time series. The runner now stamps
  all expiry snapshots with one shared timestamp per capture cycle, advancing
  the timestamp on the next cycle. This preserves cross-expiry grouping while
  retaining each cycle's observations.
- `discover_chain_for_horizon()` selects a strike window around spot using
  `strikes_per_side`; this is a strike-count selection, not a guarantee that
  both 25-delta wings are present.
- `write_option_stream()` persists the supplied snapshot rows. It does not
  enforce a complete 30D/90D surface or guarantee valid 25-delta IV observations.
- The stream runner subscribes to the underlying spot instrument as well as the
  selected option contracts. On every capture cycle it refreshes spot and the
  option LTP/bid/ask/volume/OI from the latest WebSocket state before computing
  per-contract IV and Greeks. It clears prior-cycle IV/Greeks first, so a cycle
  with no valid current price cannot inherit stale analytics. The snapshot
  timestamp remains shared across expiries for that capture cycle.
- This correction affects captures made after deployment only. It does not
  rewrite historical `option_stream` rows or establish that a 25-delta wing
  exists in the listed strike universe; the calibration export's existing
  surface completeness rules remain unchanged.

The manifest now records a per-snapshot profile: expiry date and days to expiry,
row/call/put counts, valid-IV row count, call/put delta ranges, and the presence
of ATM and 25-delta quotes under the existing tolerances. It also separates
candidate daily sessions with no snapshot, incomplete snapshots, complete
surfaces, and snapshots outside the daily candidate window. The
complete-session upper bound is now based on the intersection of candidate
sessions across price features, IVP, complete option surfaces, and realized
variance, rather than the minimum of independent source totals. These are
observational diagnostics; they do not alter the latest-snapshot rule or the
surface eligibility calculation.

This trace establishes the available code paths, not which path produced each
historical row. The source profile must be examined before changing acquisition
selection, strike coverage, capture cadence, or any legacy data. In particular,
do not infer that multi-expiry capture ran historically merely because the API
and runner exist.

