# Institutional Regime Research Evidence Bundle

**Status:** Implementation added; focused QA pending  
**Scope:** Research evidence assembly only  
**Authority:** `docs/IMPLEMENTATION_CHARTER.md`, sections 6, 8, 12 and 15

## 1. Purpose

The institutional-regime plugin already produces the four-component observation and
the decision loop persists it in `decision_evidence`. The loop also retains the
exact `evidence_id` in the decision audit. This workflow promotes those pinned
observations into a reproducible research review artifact without adding a second
operational writer or changing the decision loop.

The workflow is:

```text
InstitutionalRegimePlugin
        |
        v
DecisionLoop / EvidencePluginRunner
        |
        v
decision_evidence (first-write-only institutional_regime row)
        |
        | exact evidence_id pins; read-only query
        v
Institutional Regime Evidence Bundle
        |
        +--> coverage and component-state summary
        +--> classifier/source-vocabulary provenance
        +--> content SHA-256 and deterministic bundle ID
        +--> human review packet (PENDING_HUMAN_REVIEW)
```

## 2. Build the bundle

Run after the decisions database writer has stopped, or against an immutable
copy/export of that database. The command opens the database read-only. It must
not compete with the paper-loop writer for the same DuckDB file.

Example:

```powershell
uv run python scripts/build_institutional_regime_evidence_bundle.py `
  --db-path data/operational/decisions.duckdb `
  --symbol NIFTY `
  --start 2026-11-01T00:00:00Z `
  --end 2026-11-29T00:00:00Z `
  --output data/research/institutional_regime_nifty_2026-11.json
```

The time window is half-open: `[start, end)`. Both timestamps must include an
explicit UTC offset. The command selects only `plugin='institutional_regime'`
for the requested symbol and period.

Outputs:

- JSON bundle: exact source evidence pins and full source payloads.
- Markdown review report: availability, completeness, canonical-label frequency,
  component-state distributions, provenance and governance findings.

The bundle ID is deterministic for the exact normalized contents and source pins.
The SHA-256 covers the canonical JSON payload before the bundle ID and digest are
added. Rebuilding the same source window produces the same bundle ID.

## 3. Evidence contract

The builder rejects source rows that violate any of these conditions:

- Missing exact evidence pin, run ID, symbol, timestamp or payload.
- Envelope/payload symbol or availability mismatch.
- Evidence timestamp outside the requested window.
- Payload `as_of` later than the persisted decision timestamp or outside the window.
- Missing provisional-threshold, research-only, observation-mode or explicit
  non-eligibility flags.
- Noncanonical composite label, incomplete evidence carrying a label, or a
  complete observation without a registry-valid four-component label.
- Duplicate evidence pins or an empty source window.

Incomplete and unavailable observations are retained as evidence; they are not
silently dropped or converted into a regime label.

## 4. Governance boundary

The artifact is a **research review candidate**, not a published Gold artifact.
Its default state is:

- `review_status = PENDING_HUMAN_REVIEW`
- `artifact_status = CANDIDATE_NOT_PUBLISHED`
- `thresholds_provisional = true`
- `research_only = true`
- `eligibility_approved = false`
- `decision_eligibility_asserted = false`
- `paper_trading_approval_asserted = false`
- `live_trading_approval_asserted = false`

The v4 IV, term-structure and skew producers remain semantically uncalibrated.
Their vocabulary mapping is not a measurement correction. The v5 daily price-action
classifier remains provisional and research-only. A canonical label means that
the four tokens match the registry; it does not mean the thresholds or inputs are
calibrated.

This workflow does not:

- Change classifier thresholds or classifier versions.
- Approve or publish a Gold artifact.
- Change strategy allowlists, risk policy, or evidence-plugin runtime mode.
- Grant strategy eligibility, paper-trading approval, or live-trading authority.
- Backfill or mutate operational decision evidence.

## 5. Focused acceptance

Run:

```powershell
uv run pytest -q tests/research/test_institutional_regime_evidence.py
uv run ruff check src/nse_quant/research/institutional_regime_evidence.py scripts/build_institutional_regime_evidence_bundle.py tests/research/test_institutional_regime_evidence.py
uv run mypy src/nse_quant/research/institutional_regime_evidence.py scripts/build_institutional_regime_evidence_bundle.py
```

Then validate the command against a quiescent copy of a decisions database containing
institutional-regime evidence. Verify that the output bundle pins the same evidence
IDs visible in the decision audit and that its checksum is reproducible.

Full-suite QA and operational paper-loop validation remain separate acceptance gates.
