# NSE Quant Decision Platform

Local single-user NSE/NFO options decision and paper-trading platform.

## Status

v0.3.0 is paper-trading only. Live order placement is structurally disabled.

## Safety defaults

- `DRY_RUN=true`
- `TRADING_ENABLED=false`
- `PAPER_TRADING=true`
- `PaperBroker` is the only executable broker.
- `KiteBroker` raises `LiveTradingDisabledError` for every mutating operation.
- Strategies emit `TradeProposal` objects only.

## Configuration

- `config/settings.yaml`: version-controlled, non-secret configuration.
- `.env`: secrets and local overrides only.
- `src/nse_quant/core/constants.py`: immutable domain constants.

## Install

```bash
uv sync --extra dev
cp .env.example .env
```

## Test

```bash
uv run pytest
```

## Run Dash console

```bash
uv run python scripts/run_dashboard.py
```

## Run paper loop

```bash
uv run python scripts/run_paper_loop.py --seconds 120
```

## Check Kite stream

```bash
uv run python scripts/run_stream_check.py --seconds 120
```

## Import legacy IV history

```bash
uv run python -m nse_quant.features.historical_importer \
  --legacy-db data/options_market_data.db \
  --table option_stream \
  --dry-run
```

Remove `--dry-run` only after validating the preview.