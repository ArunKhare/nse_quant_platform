# Legacy regime-policies Silver

Persisted, source-linked Silver over the plural whole-table `regime_policies` Bronze reader.

- Store: `legacy-regime-policies-silver-recording@1`
- Command: `persist.legacy_regime_policies_silver@1`
- Source: `read_regime_policies_bronze` (plural, no layout pin)
- Retained: exact reviewed record bytes plus context and ordinal coverage
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained policy Silver is not policy truth, authorization, or execution replay
- No materialized scalar reinterpretation; layout-explicit variant remains separate
