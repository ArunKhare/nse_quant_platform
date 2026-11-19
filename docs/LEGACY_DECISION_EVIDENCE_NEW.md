# Legacy decision evidence

Decision-evidence layer derived only from the reviewed market Gold bundle.

## Contract

- Recording: `legacy-decision-evidence-recording@1`
- Command: `persist.legacy_decision_evidence@1`
- Each evidence revision is bound to the exact reviewed Gold bundle recording fingerprint, bundle revision id, and context hash.

## Native path

`observe_decision_evidence_bundle` reads the bundle through its public Gold reader and derives a bounded context. `persist_decision_evidence` requires two identical bundle observations, then writes one evidence set, one observation per bundle member record, and one attempt, all inside one transaction with a separate audit job.

The public reader verifies the evidence context hash, recording fingerprint, and per-member/per-record coverage. Current bundle equality remains separate from persisted evidence replay.

This layer preserves the bundle as decision-evidence input only. It does not interpret market data, prove validity, replay execution, or grant decision eligibility.
