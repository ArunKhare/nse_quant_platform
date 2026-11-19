# LLM enrichment adapter

`LLMEnrichmentAdapter` produces enrichment-only metadata for reviewed news items using an injected callable.

## Contract

- Input: reviewed news item with headline.
- Output: enrichment-only metadata with symbols, topics, sentiment, and confidence.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Rules

- Disabled adapter rejects with `llm_enrichment_disabled`.
- Missing or oversized headline is rejected.
- Missing enricher is rejected.
- Enricher output must be a dict.
- Symbols must be a list and are filtered to allowed symbols.
- Confidence must be between 0 and 1 and meet the configured minimum.
- Adapter never makes network calls; enrichment is injected and bounded.
