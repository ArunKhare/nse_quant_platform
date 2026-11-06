# LLM enrichment persistence

`LLMEnrichmentStore` persists enrichment-only metadata from the LLM enrichment adapter into a bounded `llm_enrichment` table.

## Contract

- Input: reviewed news item, enrichment payload, and LLM enrichment settings.
- Output: receipt with `INSERTED`, `DUPLICATE`, or `REJECTED` status.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Rules

- Disabled store rejects with `llm_enrichment_store_disabled`.
- Unavailable or incomplete enrichment is rejected.
- Missing headline is rejected.
- Payload size is bounded.
- Duplicate enrichment ID returns `DUPLICATE` without rewriting.
- Enrichment ID is a deterministic SHA-256 of the canonical item and provider.
