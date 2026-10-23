# Event Impact Synthesis

This document defines how the platform synthesizes the effect of news and
scheduled events on instruments of interest.

The goal is not to predict news. The goal is to answer, in a structured and
auditable way:

1. Which instruments can this event affect?
2. What market dimension is likely to change?
3. How strong and how reliable is that effect?
4. What action should the paper decision loop take?

Event impact is initially **observational evidence**. It must not create orders,
force exits, or bypass the persistent kill switch, paper mode, liquidity checks,
data-quality checks, or risk limits.

## Core model

```text
Event
  → affected instruments
  → impact dimensions
  → confidence and time window
  → recommended action
  → persisted evidence
  → later validated against outcomes
```

An event does not have one universal effect. Its impact depends on:

- Event type.
- Expected outcome versus actual outcome.
- Instrument exposure.
- Current volatility and IV regime.
- Market structure and trend.
- Time to expiry.
- Existing positions and portfolio exposure.

## Impact dimensions

For every affected instrument, synthesize these dimensions:

| Dimension | Question | Possible values |
|---|---|---|
| Direction | Is the likely price effect bullish, bearish, or conditional? | `BULLISH`, `BEARISH`, `NEUTRAL`, `CONDITIONAL` |
| Volatility | Will uncertainty or realized movement change? | `LOW`, `MEDIUM`, `HIGH` |
| Liquidity | Will spreads, depth, or participation change? | `LOW`, `MEDIUM`, `HIGH` |
| Time window | When does the effect start and decay? | Pre-event, release, post-event |
| Confidence | How reliable is the mapping? | 0.0–1.0 |
| Recommended action | What should the loop do? | `OBSERVE`, `REDUCE_SIZE`, `BLOCK_NEW_ENTRIES`, `REVIEW_OPEN_POSITIONS` |

`CONDITIONAL` direction is important. For example, an RBI rate decision is not
automatically bullish or bearish; its effect depends on the consensus expectation
and the actual decision.

## Event-to-instrument mapping

Maintain an explicit configuration mapping rather than inferring all
relationships at runtime.

```yaml
event_impact_rules:
  RBI_POLICY:
    affected:
      NIFTY:
        direction: conditional
        volatility_impact: high
        liquidity_impact: medium
        confidence: 0.85
      BANKNIFTY:
        direction: conditional
        volatility_impact: high
        liquidity_impact: medium
        confidence: 0.80

  FED_POLICY:
    affected:
      NIFTY:
        direction: conditional
        volatility_impact: high
        liquidity_impact: medium
        confidence: 0.75

  UNION_BUDGET:
    affected:
      NIFTY:
        direction: conditional
        volatility_impact: high
        liquidity_impact: medium
        confidence: 0.80

  STOCK_RESULTS:
    affected:
      "{symbol}":
        direction: conditional
        volatility_impact: high
        liquidity_impact: high
        confidence: 0.90
      "{sector_index}":
        direction: conditional
        volatility_impact: medium
        liquidity_impact: low
        confidence: 0.55
```

Examples:

| Event | Direct instrument | Secondary instruments |
|---|---|---|
| RBI policy | NIFTY, BANKNIFTY | Rate-sensitive sector indices |
| Fed policy | NIFTY | IT, metals, financials |
| Union Budget | NIFTY | Sector indices named in the budget |
| RELIANCE results | RELIANCE | NIFTY ENERGY, NIFTY |
| HDFC Bank results | HDFCBANK | BANKNIFTY, NIFTY |
| Crude-oil shock | Oil-marketing companies | NIFTY, inflation-sensitive sectors |

## Event surprise

For numeric macro events, calculate a surprise:

\[
\text{surprise} =
\text{actual value} - \text{consensus value}
\]

For qualitative events, store a normalized surprise label:

- `IN_LINE`
- `BETTER_THAN_EXPECTED`
- `WORSE_THAN_EXPECTED`
- `DOVISH`
- `HAWKISH`
- `UNKNOWN`

The impact synthesis should use the surprise, not merely the event’s existence.

### Example

| Event | Consensus | Actual | Surprise | Likely synthesis |
|---|---:|---:|---|---|
| RBI repo decision | 25 bps cut | 25 bps cut | In line | Lower uncertainty after release |
| RBI repo decision | 25 bps cut | No cut | Hawkish surprise | Bearish pressure on rate-sensitive names; higher volatility |
| Fed decision | Hawkish pause | Dovish pause | Dovish surprise | Positive risk-asset bias |
| Stock results | EPS ₹20 | EPS ₹16 | Negative surprise | Bearish for stock; possible sector spillover |

## Option-market synthesis

For NIFTY options, translate event impact into option-market measures.

| Event effect | Option-market signal |
|---|---|
| Higher uncertainty | Rising ATM IV, higher straddle price, higher expected move |
| Directional bias | Skew shift, changing PCR, OI build-up on one side |
| Event resolution | IV crush and falling expected move |
| Large gap risk | Wider wings or no new short-volatility entry |
| Expiry proximity | Higher gamma; avoid new short-volatility exposure |

Useful pre/post-event measures:

\[
\Delta IV = IV_{post} - IV_{pre}
\]

\[
\Delta ExpectedMove =
ExpectedMove_{post} - ExpectedMove_{pre}
\]

\[
\Delta PCR =
PCR_{post} - PCR_{pre}
\]

A high pre-event IV followed by a sharp post-event IV decline is classic IV
crush. This is especially relevant to short-premium strategies such as iron
condors.

## Evidence payload

Persist one synthesized record per affected instrument.

```json
{
  "plugin": "event_impact",
  "available": true,
  "event_id": "rbi_policy_2026_10_23",
  "event_type": "RBI_POLICY",
  "instrument": "NIFTY",
  "event_ts": "2026-10-23T10:00:00+05:30",
  "direction": "conditional",
  "volatility_impact": "high",
  "liquidity_impact": "medium",
  "confidence": 0.85,
  "surprise": null,
  "pre_event_iv": 0.142,
  "post_event_iv": null,
  "pre_event_expected_move_points": 185.4,
  "post_event_expected_move_points": null,
  "recommended_action": "block_new_entries",
  "reason": "high_impact_macro_event_within_blackout_window"
}
```

Allowed initial recommended actions:

- `OBSERVE`
- `REDUCE_SIZE`
- `BLOCK_NEW_ENTRIES`
- `REVIEW_OPEN_POSITIONS`

The platform should not automatically issue an order or close a position solely
because of an event. Any forced-exit behavior must be a separately tested risk
rule and must remain subordinate to the kill switch.

## Decision-loop integration

Add an `EventImpactPlugin` as an observational evidence plugin.

In `DecisionLoop.run_once()`, after feature construction and data-quality
assessment:

1. Query events in a look-ahead-safe time window.
2. Map each event to affected instruments.
3. Join current market features: spot, IV, expected move, OI, PCR, ATR, trend.
4. Synthesize direction, volatility, liquidity, confidence, and action.
5. Persist `event_impact` evidence.
6. Return an `event_risk` summary to the decision loop.

The plugin must catch its own errors and persist an unavailable payload rather
than stopping the paper loop.

### Look-ahead safety

Use only information known at decision time.

- A future scheduled event may block a new entry.
- A news article published after the decision timestamp must not influence that
  historical decision.
- Post-event market data may be used only to evaluate the event after it occurs.

## Action policy

Start with conservative, explainable rules.

| Condition | Synthesized action |
|---|---|
| High-impact macro event within blackout window | `BLOCK_NEW_ENTRIES` |
| Stock results within blackout window | `BLOCK_NEW_ENTRIES` for that stock |
| Event likely to raise volatility | `REDUCE_SIZE` or `BLOCK_NEW_ENTRIES` for short-volatility strategies |
| Event passed and IV falls sharply | `REVIEW_OPEN_POSITIONS` |
| News sentiment is negative but no scheduled event | `OBSERVE` |
| Event affects a related sector but not the traded instrument | `OBSERVE` |

Initially, only `BLOCK_NEW_ENTRIES` should be considered for promotion to a hard
eligibility restriction, and only for explicitly configured high-impact events.

## Data model

### Market events

```sql
CREATE TABLE IF NOT EXISTS market_events (
    event_id VARCHAR PRIMARY KEY,
    source VARCHAR,
    event_type VARCHAR,
    title VARCHAR,
    description TEXT,
    symbol VARCHAR,
    event_ts TIMESTAMPTZ,
    importance VARCHAR,
    consensus_value DOUBLE,
    actual_value DOUBLE,
    surprise_label VARCHAR,
    affected_underlyings JSON,
    raw_payload JSON,
    ingested_at TIMESTAMPTZ
);
```

### Event impact evidence

```sql
CREATE TABLE IF NOT EXISTS event_impact_evidence (
    impact_id VARCHAR PRIMARY KEY,
    run_id VARCHAR,
    ts TIMESTAMPTZ,
    event_id VARCHAR,
    event_type VARCHAR,
    instrument VARCHAR,
    direction VARCHAR,
    volatility_impact VARCHAR,
    liquidity_impact VARCHAR,
    confidence DOUBLE,
    surprise_label VARCHAR,
    recommended_action VARCHAR,
    payload JSON
);
```

## Validation

After each event, record the observed market reaction:

- Spot return over 5, 15, 30, and 60 minutes.
- Realized range.
- ATM IV change.
- Expected-move change.
- PCR change.
- OI change at relevant strikes.
- Option spread change.
- Strategy P&L impact, if a position was open.

Then evaluate whether the pre-event synthesis was useful:

- Did `BLOCK_NEW_ENTRIES` avoid poor iron-condor entries?
- Did high-volatility warnings precede larger adverse moves?
- Did IV-crush warnings precede favorable short-premium outcomes?
- Did sector spillover predictions hold?

Promote a rule to a hard gate only after it improves risk-adjusted outcomes
across enough events and market regimes.

## Implementation roadmap

### Phase 1: Scheduled-event evidence

- Add `market_events` and `event_impact_evidence` tables.
- Ingest only manually approved or licensed event sources.
- Map RBI, Fed, Budget, expiry, and major stock results.
- Persist `event_impact` evidence in the paper loop.

### Phase 2: Event reaction research

- Capture pre- and post-event IV, expected move, OI, PCR, spot, and range.
- Build an event-outcome research panel.
- Measure iron-condor performance around events.

### Phase 3: Risk-policy integration

- Enable configurable blackout windows for selected high-impact events.
- Add event-aware position-size reduction.
- Add event-aware review alerts for open positions.

### Phase 4: News enrichment

- Add licensed news ingestion.
- Use an optional LLM enrichment step to extract symbols, topics, sentiment, and
  event relevance.
- Store model output as enrichment only; retain the original source and raw
  payload for auditability.

## Safety boundary

Event synthesis must never:

- Enable live trading.
- Bypass the persistent kill switch.
- Override paper or dry-run mode.
- Ignore liquidity or data-quality failures.
- Automatically place, modify, or cancel orders.
- Force-close a position without an explicitly tested risk rule.

The first production-safe version is:

```text
scheduled event
  → mapped affected instruments
  → synthesized impact evidence
  → block or reduce new paper entries where configured
  → record actual market reaction
  → validate the rule before expanding it
```
