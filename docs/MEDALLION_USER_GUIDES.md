# Medallion Platform User Guides

## Developer guide

### Purpose

Developers implement and extend Medallion modules without weakening contracts or safety boundaries.

### Rules

- Keep contracts module-local.
- Keep `DatasetContract` immutable.
- Use explicit versioning.
- Use exact replay.
- Reject `POINT_IN_TIME_DECISION`.
- Return `decision_eligibility_asserted=False`.
- Do not grant live trading, healing, backfill, adoption, deletion, production cutover, or execution authority.

### Where to add a new dataset

1. Create a new module under `src/nse_quant/data_platform/`.
2. Define `VERSION`, `COMMAND`, `DOMAIN`, `TABLES`, and `CONTRACT`.
3. Use the appropriate `Layer` and `WritePolicy`.
4. Implement first-write, audit, orphan-check, and final-audit obligations.
5. Implement exact replay.
6. Add tests under `tests/data_platform/`.
7. Add documentation under `docs/`.

### Where to add settings

Add only operational settings to `config/settings.yaml` and `MedallionSettings` in `src/nse_quant/core/settings.py`.

Do not move contracts into YAML.

## Quant researcher guide

### Purpose

Researchers use evidence, features, and research modules to understand market behavior without granting decision eligibility.

### Available research

- Cash-stock swing signals.
- Corporate actions and earnings calendar.
- Stock-option liquidity.
- Stock-option event risk.
- Stock-option defined-risk strategies.
- Stock-option execution quality.
- Stock-option launch readiness.

### Safety

All research modules are observational and return `decision_eligibility_asserted=False`.

## Operations guide

### Purpose

Operations runs and monitors the platform.

### Daily checklist

1. Confirm paper mode.
2. Confirm kill switch.
3. Confirm market hours.
4. Confirm Medallion layers.
5. Run QA.
6. Run paper loop.
7. Review dashboard.
8. Review evidence and governance.
9. Review positions and exits.
10. Run EOD maintenance.

### Incident policy

Never bypass a refusal. Investigate the original obligation instead.

## Risk and compliance guide

### Purpose

Risk and compliance review safety boundaries, governance, and operational holds.

### Key controls

- Persistent kill switch.
- Paper-only mode.
- Dry-run behavior.
- Market-hours enforcement.
- Data-quality gates.
- Liquidity gates.
- Strategy and portfolio risk limits.
- EOD review and warehouse exports.

### Non-negotiables

- `POINT_IN_TIME_DECISION` rejected.
- `decision_eligibility_asserted=False`.
- No live trading without explicit authorization.
- No healing, backfill, adoption, or deletion.
- No production cutover without governance authorization.

## Trader guide

### Purpose

Traders use the paper loop and dashboard to understand strategy behavior.

### What you see

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

### What you cannot do

- Place live orders.
- Approve execution.
- Bypass kill switch.
- Force eligibility.
- Authorize production cutover.

## Auditor guide

### Purpose

Auditors verify evidence, governance, replay, and operational acceptance.

### What to verify

- Bronze immutability.
- Silver source linkage.
- Gold versioning.
- Publication completeness.
- Admission refusal boundaries.
- Governance final audit.
- Exact replay.
- Operational acceptance.
- Controlled execution boundary.
- Expansion boundaries.

## Document map

| Document | Audience |
|---|---|
| `docs/MEDALLION_ARCHITECTURE_DESIGN.md` | All users |
| `docs/MEDALLION_OPERATIONAL_GUIDE.md` | Operations, traders |
| `docs/CURRENT_NATIVE_STATUS.md` | All users |
| `docs/CONFIGURATION.md` | Developers, operations |
| `README.md` | All users |
