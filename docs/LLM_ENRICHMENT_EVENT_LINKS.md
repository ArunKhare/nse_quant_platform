# LLM enrichment-to-event links

`LLMEnrichmentEventLinker` links LLM enrichment metadata to a reviewed market event within a configured time window.

## Contract

- Input: enrichment ID, event ID, instrument, event timestamp, and observed timestamp.
- Output: receipt with `LINKED`, `DUPLICATE`, or `REJECTED` status.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Rules

- Disabled linking rejects with `llm_enrichment_linking_disabled`.
- Link window is bounded by `max_link_window_minutes`.
- Both enrichment and event must already exist.
- Duplicate link ID returns `DUPLICATE` without rewriting.
- Link ID is a deterministic SHA-256 of enrichment ID, event ID, and instrument.
