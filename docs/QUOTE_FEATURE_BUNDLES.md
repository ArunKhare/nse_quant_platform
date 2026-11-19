# Immutable quote-feature bundle candidates @1

## Scope and interfaces
assemble_quote_bundle(bronze, frame_silver, reference_silver, assessments, gold,
    build_ids=(<explicit SHA256>, ...)) -> QuoteFeatureBundle

Read-only caller-owned connections, no outer transactions. Uses the native Gold
consumer, not SQL shortcuts, cached results or legacy-workspace adapters.
make_quote_bundle(members) and encode/decode_quote_bundle are pure content APIs.
They validate content integrity, NOT authenticity, current source validity or
publication authority. read_quote_bundle_file is a bounded read of an acquired
artifact; it creates nothing. This package has no staging/publish/write command.

## Membership and stability
1..64 explicit, unique Gold build pins, sorted canonically; no latest selection,
partial output, missing-member omission, first/last wins or automatic retries.
Every member must be verified_current AND candidate, with the exact expected
Gold reader version, active build pin and nonempty successful attempt evidence.
Candidate/blocked disposition is not confused with verification status.

Snapshot full canonical candidate JSON (features, quality, times and lineage),
its SHA256, Gold evidence fingerprint, reader version and successful job IDs.
Reject repeated (source frame revision, packet ordinal, feature version) keys,
even if distinct build/assessment pins would otherwise hide duplicate features.
Two sequential verification passes must observe identical member snapshots.
Observed drift blocks the whole assembly, not only one member.

Two passes are NOT an atomic cross-database snapshot, simultaneous market
observation, as-of information frontier or publication barrier. A source can
change after its final read. Members can represent different event instants;
this bundle does not align markets, assert freshness or grant temporal validity.
Underlying reader limits/costs apply twice per member; no throughput claim.

## Exact manifest identity
Manifest version quote-feature-bundle@1. The manifest contains canonical sorted
member records, membership fingerprint and explicit non-publication/eligibility
flags. bundle_id is SHA256 of the EXACT encoded manifest bytes. It is not embedded
inside those bytes, avoiding circular hashes and matching content-addressed file
naming. The immutable dataclass carries bundle_id as external identity metadata.

Membership fingerprint = SHA256(canonical([bundle version, sorted build pins])).
Candidate JSON retains its original Gold build_id rule (hash with build_id="").
A separate candidate_sha256 addresses its full exact bytes. Gold evidence changes
can create a new bundle even when numerical prices and build IDs are unchanged.
No current wall clock, random ID or inferred publication time enters the manifest.

## Strict decoding and bounds
Duplicate JSON keys/nonfinite values, noncanonical encodings, unknown schemas or
versions, wrong IDs/hashes, duplicate membership/packet keys, false numeric types,
wrong fixed-point prices/ranges/quality flags and manufactured temporal/identity
claims reject. Decimal prices remain strings plus integer ratios, never floats.
Unknown event/trade times remain null; zero observations stay zero, negative
inverted ranges remain negative with their original quality flags.

Candidate schemas are explicitly version-pinned. New candidate fields/versions
require deliberate bundle-contract review, not silent compatibility acceptance.
Limits: 64 members, 1 MiB/candidate JSON, 4 MiB/manifest, 1000 successful job IDs
per member with bounded identifier syntax. Artifact reads request at most the
bundle limit +1 byte before rejecting. Invalid IDs reject before file access.
No unbounded ManifestStore.read is used; ManifestStore itself is untouched.
Use trusted paths: checksum validation is not signature/authentication, symlink
protection or authority to expose an artifact to decisions.

## Publication and replay boundary
published_at=null; publication_asserted=false; historical_validity_asserted=false;
decision_eligibility_asserted=false. A mathematical/content-valid offline bundle
can be constructed by anyone and is NOT a trusted published feature bundle.
Source-verifying assembly is a distinct path; it still does not publish.

No filesystem writes, domain DB writes or audit transitions occur in this package.
Next: audited durable staging/sealing and separately authorized publication with
reviewed temporal admission. Existing ManifestStore offers no-replace visibility,
not an end-to-end power-loss durability or publication-authority guarantee.
These candidate manifests snapshot Gold values and lineage, not all upstream raw
evidence/code/config needed for complete exact decision replay. No replay claim.
Data loading/migration stays held until platform acceptance gates pass.
