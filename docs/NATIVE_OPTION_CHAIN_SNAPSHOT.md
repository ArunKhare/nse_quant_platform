# Native option-chain snapshot

Native retained option-chain snapshot Bronze and Silver.

- Codec: `native-option-chain-snapshot@1`
- Bronze: `native-option-chain-snapshot-bronze-recording@1`, command `ingest.native_option_chain_snapshot@1`
- Silver: `native-option-chain-snapshot-silver-recording@1`, command `persist.native_option_chain_snapshot_silver@1`
- Retained: exact reviewed snapshot artifact and per-quote records with context and ordinal coverage
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained snapshot is not market truth, option pricing truth, or execution replay
- No positive decision eligibility; `decision_eligibility_asserted=False` always
