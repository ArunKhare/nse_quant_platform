# NSE Quant Decision Platform

Local single-user NSE/NFO options decision and paper-trading platform.

## Configuration

- `config/settings.yaml`: global, version-controlled parameters.
- `.env`: secrets and local overrides only.
- `core/constants.py`: immutable domain constants.
- `core/settings.py`: typed validated configuration; precedence `.env` > YAML > defaults.

## Quick start

```bash
uv sync --extra dev
cp .env.example .env
uv run pytest
uv run python -m ui.dash_app
uv run python -m market_data.kite_stream --seconds 120
uv run python -m core.loop --seconds 120
```
