# Medallion Architecture Design

## Purpose

This document defines the hybrid Medallion architecture for the NSE Quant Decision Platform. It separates immutable data contracts from operational settings, preserves exact replay and governance boundaries, and provides a clear path from received artifacts to native decisions.

## Architecture

```text
Received artifacts
  -> immutable Bronze
  -> typed source-linked Silver
  -> versioned Gold
  -> published bundles
  -> native decisions
  -> exact replay
```

## Core principle

Contracts are module-local. Operational settings are centralized.

- Contracts define what a dataset is, how it may be written, and how it must be replayed.
- Settings define whether a Medallion path is enabled, where it lives, and which operational mode is active.
- Settings must never weaken a contract or safety boundary.

## Layers

| Layer | Write policy | Required metadata | Ownership |
|---|---|---|---|
| Bronze | Append observations | received_at, source, payload_hash | Source capture |
| Silver | Append revisions | recorded_at, source_observation_id, revision_id | Typed source-linked transformation |
| Gold | Versioned builds | build_id, event_ts, published_at, feature_version | Versioned analytical build |
| Publication | Controlled publication | Complete evidence and publication candidate | Publication service |
| Admission | Controlled admission | Explicit acceptance, no point-in-time decision | Admission service |
| Governance | Audit, retention, replay | Final audit, exact replay | Governance service |
| Execution | Controlled execution | Explicit authorization, paper default | Execution gateway |
| Expansion | Controlled expansion | Underlying and strategy boundaries | Expansion service |

## Contract model

`DatasetContract` remains the authoritative contract object.

```python
@dataclass(frozen=True)
class DatasetContract:
    name: str
    version: str
    layer: Layer
    write_policy: WritePolicy
    entity_keys: tuple[str, ...]
    required_columns: tuple[str, ...]
    owner: str
```

Contracts must remain immutable and module-local. They must not be configurable through YAML.

## Settings model

Add a `medallion` section to `config/settings.yaml` and a `MedallionSettings` model to `src/nse_quant/core/settings.py`.

```yaml
medallion:
  enabled: true
  root_path: data/medallion
  bronze:
    enabled: true
    root_path: data/medallion/bronze
    max_payload_bytes: 262144
    require_original_first_write: true
  silver:
    enabled: true
    root_path: data/medallion/silver
    max_revision_bytes: 262144
    require_source_link: true
  gold:
    enabled: true
    root_path: data/medallion/gold
    require_versioned_build: true
    require_published_bundle: true
  publication:
    enabled: true
    require_complete_evidence: true
  admission:
    enabled: true
    require_explicit_acceptance: true
    reject_point_in_time_decision: true
  governance:
    enabled: true
    retention_days: 365
    require_final_audit: true
    require_exact_replay: true
  execution:
    mode: paper
    live_enabled: false
    require_explicit_user_authorization: true
    kill_switch_enforced: true
  expansion:
    enabled: true
    underlyings: [NIFTY, BANKNIFTY]
    stock_options_enabled: false
    stocks_enabled: false
    spreads_enabled: false
    multi_leg_strategies_enabled: false
```

## Safety boundaries

- `POINT_IN_TIME_DECISION` remains rejected.
- `decision_eligibility_asserted` remains `False`.
- No eligibility, live trading, healing, backfill, adoption, deletion, production cutover, or execution authority is granted by settings.
- Original failed, incomplete, unlinked, or orphan obligations are not healed by later success.
- Live execution requires explicit configuration and explicit user authorization.
- Package QA is not platform acceptance.

## Governance chain

```text
Evidence
  -> acceptance/reconciliation
  -> decision-loop linkage
  -> real accepted-authority integration
  -> completeness report
  -> audit trail
  -> final audit
  -> end-to-end validation
  -> platform acceptance
  -> release readiness
  -> production cutover readiness
  -> operational cutover authorization
  -> production cutover execution authorization
  -> execution readiness
  -> execution completion
```

## User roles

| Role | Primary need | Documents |
|---|---|---|
| Developer | Implement and extend modules | Design doc, module contracts |
| Quant researcher | Understand evidence and strategy inputs | Evidence docs, research docs |
| Operations | Run and monitor the platform | Operational doc |
| Risk/compliance | Understand safety and holds | Governance and safety sections |
| Trader | Understand paper loop and execution boundary | Operational doc |
| Auditor | Verify replay and governance | Governance doc |

## Implementation rule

Do not move contracts into YAML. Do not allow YAML to weaken contracts. Centralize only safe operational settings.
