# Medallion Platform Operational Guide

## Purpose

This guide explains how to install, configure, run, monitor, and operate the NSE Quant Decision Platform using the Medallion architecture and the existing paper decision loop.

## Prerequisites

- Windows with Python 3.12+.
- `uv` installed.
- Kite API credentials in `.env` if market data ingestion is required.
- Telegram credentials in `.env` if notifications are required.

## Installation

```powershell
cd C:\Projects\nse_quant_platform
uv sync
```

Verify interpreter:

```powershell
uv run python -c "import sys; print(sys.executable); print(sys.version)"
```

## Configuration

Create `.env` in the repository root:

```env
KITE_API_KEY=your_kite_api_key
KITE_API_SECRET=your_kite_api_secret
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
```

Do not put secrets in YAML.

## Safe defaults

The base configuration is paper-safe:

```yaml
safety:
  dry_run: true
  trading_enabled: false
  paper_trading: true
```

Medallion defaults are also paper-safe:

```yaml
medallion:
  execution:
    mode: paper
    live_enabled: false
```

## Run QA

```powershell
uv run pytest tests/data_platform -q
uv run pytest tests -q
uv run ruff check .
uv run mypy .
git diff --check
```

## Run the paper loop

```powershell
uv run python -m nse_quant
```

Open the dashboard:

```text
http://127.0.0.1:8050
```

## Medallion data flow

```text
Kite / received artifacts
  -> Bronze
  -> Silver
  -> Gold
  -> Publication
  -> Admission
  -> Native decision
  -> Exact replay
```

## Daily operations

1. Confirm kill switch is clear.
2. Confirm paper mode is active.
3. Confirm market hours enforcement.
4. Confirm Medallion layers are enabled.
5. Run the paper loop.
6. Review dashboard.
7. Review evidence completeness.
8. Review governance status.
9. Review open positions and exits.
10. Run EOD maintenance and warehouse exports.

## Monitoring

The dashboard shows:

- Execution mode.
- Live trading blocked.
- Kill switch.
- Loop status.
- Strategy eligibility.
- Data quality.
- IV history.
- Market metrics.
- IV smile.
- Open positions.

Governance status can be added as a read-only dashboard section.

## Incident response

| Situation | Action |
|---|---|
| Data quality degraded | Do not force eligibility; investigate source. |
| Evidence incomplete | Do not backfill or heal; investigate original obligation. |
| Kill switch active | Stop new order creation; investigate before reset. |
| Admission refused | Do not bypass; review Gold and reconciliation. |
| Execution refused | Do not bypass; review authorization and mode. |
| Live trading requested | Keep disabled unless a separately authorized cutover is approved. |

## Safety rules

- Paper-only by default.
- Live trading structurally disabled.
- Persistent kill switch.
- Market-hours enforcement.
- Data-quality gates.
- Liquidity gates.
- Strategy and portfolio risk limits.
- EOD review and warehouse exports.

## Production cutover

Production cutover remains held. Do not enable live trading, production publication, or decision-loop cutover without a separately authorized governance decision.

## Support

Refer to:

- `docs/MEDALLION_ARCHITECTURE_DESIGN.md`
- `docs/CURRENT_NATIVE_STATUS.md`
- `docs/CONFIGURATION.md`
- `README.md`
