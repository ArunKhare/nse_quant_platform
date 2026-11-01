# Immutable quote-feature bundle construction package

## Interpretation / baseline reconciliation
This is the next package after uploaded native Gold consumption, not a redelivery
of the consumer. Last explicit Git marker remains b23cf45. The Gold consumer is
present in uploaded sources, but its separate commit/QA status was not supplied;
local HEAD/branch cannot be independently verified here. Do not assume or overwrite.

This turn inspected current gold_quote_reader.py exact GoldQuoteEvidence/API,
Gold build CLI and manifests.py hard-link/no-replace/fsync semantics. The new
package uses the actual uploaded consumer interface. Gold kernel model fields are
from prior user-confirmed package/API; no kernel or consumer replacements shipped.
Existing ManifestStore is unchanged. No migration or loading is performed.

## Add only
src/nse_quant/data_platform/feature_bundle.py
src/nse_quant/data_platform/quote_bundle_assembly.py
tests/data_platform/test_feature_bundle.py
docs/QUOTE_FEATURE_BUNDLES.md

## Implemented
- Frozen member and bundle models with exact serialized Gold candidate snapshots.
- Explicit sorted/unique 1..64 membership, no semantic duplicate packet features.
- Canonical JSON bytes and SHA256 bundle IDs without self-referential hashing.
- Full candidate/build/ratio/lineage/quality/schema validation and strict decoding.
- Read-only all-or-nothing assembly using two source-verification passes.
- Bounded acquired-artifact reader; no files/database/audit writes or publication.

Public API:
assemble_quote_bundle(bronze, frame_silver, reference_silver, assessments, gold,
    build_ids=(<exact build pin>, ...))
encode_quote_bundle(bundle) -> exact bytes
decode_quote_bundle(raw, expected_bundle_id=<exact pin>) -> content-validated bundle
read_quote_bundle_file(root, bundle_id=<exact pin>) -> content-validated bundle

The pure codec is NOT a provenance/current-state/publication verifier. Only the
assembly path calls source-verifying Gold readers. Two matching passes are not
atomic across sources or a decision-admission barrier. No fallback/retry occurs.
Unknown times remain null and all publication/validity/eligibility assertions false.
See docs/QUOTE_FEATURE_BUNDLES.md for complete scope, bounds and trust boundaries.

## Verification performed
60 focused tests passed on Python 3.12.8. New codec and assembly code ran directly:
round trips/exact IDs, deterministic ordering, duplicate semantics, strict JSON,
content hashes/schema/temporal claims, exact decimals/ranges/zeros, scale extremes,
quality flags, immutable snapshots, byte/member bounds and bounded artifact reads.
Assembly tests substitute the Gold reader boundary, checking exact pins/two passes,
blocked members, drift detection, no retry or partial results and exception handling.
Sandbox baseline dataclass interfaces were replicated from inspected/conversation
source with a fail-fast reader placeholder. Harness files are NOT shipped. Real
repository tests import its actual committed models. This is not end-to-end DB
or publication verification. Full repository QA, Ruff and mypy were not run here.
Line lengths, staged patch whitespace and archive/file checksums were checked.

## Safe application and mandatory QA
Inspect git branch --show-current, git log -1 and git status --short in
C:\Projects\nse_quant_platform. Require feat/medallion-feature-store and reconcile
current HEAD (b23cf45 or newer) without resetting/discarding work. Confirm local
Gold consumer exists with the inspected API. Copy ONLY four repository additions;
STOP if a path exists and compare rather than overwrite. Preserve committed fixes.
Run verify-local.ps1 from extracted bundle. It runs focused tests and all five
required QA commands. Review untracked additions; diff --check alone ignores them.
No dependencies, existing tests, architecture or typing rules are changed/weakened.

Suggested commit after local QA:
feat(data-platform): construct immutable pinned quote-feature bundles

No audited staging, sealing/publication lifecycle, temporal admission, decisions or
exact replay are claimed complete. Loading/migration remains deferred.
