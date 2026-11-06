# News enrichment persistence

`NewsEnrichmentStore` persists enrichment-only metadata for reviewed news items into a bounded `news_enrichment` table.

## Contract

- Input: reviewed news item and enrichment payload.
- Output: receipt with `INSERTED`, `DUPLICATE`, or `REJECTED` status.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Rules

- Disabled store rejects with `news_enrichment_disabled`.
- Unavailable enrichment is rejected.
- Missing headline is rejected.
- Duplicate enrichment ID returns `DUPLICATE` without rewriting.
- Enrichment ID is a deterministic SHA-256 of the canonical reviewed item.
