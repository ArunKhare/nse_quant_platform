# Configuration

## Precedence

1. Environment variables / `.env` — secrets and machine-specific overrides.
2. `config/settings.yaml` — version-controlled global parameters.
3. Pydantic defaults — safe fallbacks.

## Placement

| Value type | Location | Examples |
|---|---|---|
| Secrets | `.env` only | Kite API key/secret, Telegram token |
| Global parameters | `config/settings.yaml` | IV thresholds, risk limits, wing distance, paths, notifier enablement |
| Immutable constants | `core/constants.py` | Market hours, annualization, solver bounds |
| Per-run overrides | CLI | `--seconds`, `--config` |
| Strategy parameters | `strategy:` YAML section | `iron_condor_monitor.wing_distance_points` |

## Rules

- Never put credentials in YAML or commit a real `.env`.
- Configure Telegram notifications with `notifier.enabled` and `notifier.telegram.enabled`; keep `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`.
- Do not hardcode thresholds in analytics, strategy, risk, or UI modules.
- Add a typed field to the relevant Settings section, update `config/settings.yaml`, and add a test.
