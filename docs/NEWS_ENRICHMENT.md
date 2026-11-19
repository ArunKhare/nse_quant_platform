# News enrichment

`enrich_news_item` produces bounded, offline enrichment metadata for reviewed news items.

## Contract

- Input: reviewed news item with a headline and `NewsEnrichmentSettings`.
- Output: enrichment-only payload with symbols, topics, sentiment, and relevance confidence.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Rules

- Disabled enrichment returns unavailable with reason `news_enrichment_disabled`.
- Missing or oversized headline returns unavailable with a clear reason.
- Symbols are matched only against the configured allowlist.
- Topics and sentiment use bounded keyword sets.
- Relevance confidence is capped at 1.0.
