# Source-pinned derivative descriptions @1

## Reconciliation and placement

Latest USER-REPORTED baseline: 233a117 on feat/medallion-feature-store and origin,
QA/tests passed. No local repository access; branch/HEAD and committed contents
were not independently verified. Uploaded admission_frontier.py and its actual
Windows-safe ATTACH-alias tests were inspected. They are preserved, not replaced.

Native reference reader lookup_native_reference returns a NativeReferenceLookup
with UNIQUE_TOKEN_ROW pins and explicitly canonical_contract_id=None. Its typed
CSV row is ReferenceRow from kite-native-reference-csv@1, with nullable decimal
strings/expiry, exact source_fields_hash, provider_name, segment/exchange/type.
There is no canonical underlying pin in that row. This package therefore implements
the descriptive prerequisite to canonical identity, NOT a fabricated authoritative
contract registry or a provider-token-as-contract shortcut. No legacy adapter work.

This is a pure kernel and native read-only consumption service. It creates no new
Bronze/Silver/Gold records or database. No schema/Layer/dependency changes. Existing
source payloads, reference contracts, normalization versions and audits are untouched.

## Pure API and policy

    describe_derivative_row(
        assessment_revision_id=<exact pin>,
        frozen_row_json=<canonical complete typed ReferenceRow JSON>,
    ) -> DerivativeDescription

Version: provider-derivative-description@1. The immutable DEFINITION and fingerprint
are embedded in results. Scope is intentionally limited to explicit triples:
NFO/NFO-OPT/CE, NFO/NFO-OPT/PE, NFO/NFO-FUT/FUT. This is a versioned scope choice,
not a claim to cover all NSE instruments. Other triples produce unsupported.

Provider_name must be an explicit bounded uppercase supported label. Missing or
unsupported labels produce unresolved. Trading symbols are retained but NEVER
parsed for expiry, underlying, strike or contract type. No alias table or first/last
wins behavior. Different labels such as NIFTY and NIFTY50 are not silently merged.
No canonical_underlying_id or canonical_contract_id is manufactured.

Expiry is an exact calendar date. It is not converted to exchange close, expiry
instant, economic validity interval or availability. Missing expiry, zero lot size,
missing/nonpositive tick size, missing/nonpositive option strike remain unresolved.
For FUT only, absent or zero strike does not enter its descriptive key; nonzero
future strike is inconsistent. All original values remain frozen, including zero.
No blank field is silently converted to zero. Unsupported/inconsistent/unresolved
observations retain deterministic descriptions with no provider_description_key.
Malformed schemas/types/decimals/dates exceed this domain contract and raise.

Full native typed row is frozen, including last price, token, exchange token, lot,
tick, trading symbol and original source hash. This is not original CSV/wire bytes;
those remain upstream. source_fields_hash is preserved, not recomputed from typed
fields: converting original numeric lexemes to typed integers can lose leading zeros.

Exact unsigned decimal syntax (no float/exponent/negative/nonfinite) is normalized
with string operations, without Decimal context rounding. Leading integer zeros
and trailing fractional zeros are removed for descriptive comparison only. A large
strike retains every digit. Full original decimal strings remain in the frozen row.

## Keys, evidence identity and collisions

provider_description_key hashes version, venue/segment/type, exact provider label,
expiry date and normalized option strike (none for FUT). It is a descriptive bucket,
NOT canonical contract identity, proof of equivalent instruments or a global unique
key. Token, lot, tick, price and symbol are not descriptive key components.

The description_id hashes the complete result excluding description_id itself,
including definition fingerprint, assessment pin and full exact typed-row JSON.
Every source-row or input change remains visible in this identity, including lot,
tick, symbol, price or token differences even when the descriptive key is equal.
Multiple observations with one descriptive key MUST remain separate evidence.
No aggregation, deduplication, collision-resolution or unique-contract API is supplied.
A later audited identity-binding registry must handle those conflicts explicitly.

## Codec / trust

    encode_derivative_description(value) -> bytes
    decode_derivative_description(raw, expected_description_id=<pin>) -> description

Strict canonical JSON, duplicate/nonfinite rejection, full field schema, deterministic
recomputation and type-sensitive canonical result equality. Unknown/additional fields
or a bool/int authority substitution fail. Decode is offline consistency only:
a self-hashed row can still be fictional. It cannot restore provenance or authority.
Pure provenance_verified, availability, publication, historical-validity and
 decision-eligibility flags remain false; canonical IDs remain None.
Typed row <=64 KiB, individual source text fields <=4096 characters, decimal <=64
characters, encoded description <=128 KiB. No partial salvage or caller override.

## Native read-only consumer

    read_native_derivative_description(
        bronze, silver,
        assessment_revision_id=<exact native HTTP reference assessment pin>,
        instrument_token=<explicit provider token>,
    ) -> NativeDerivativeDescription

Owned file-backed read-only connections, no enclosing transaction. No DB/file/
network creation or writes. Native CSV version must remain @1. Sequence:
1. Call existing native lookup (which resolves invalidation history before quality
   selection and recomputes current source reference evidence).
2. Require UNIQUE_TOKEN_ROW and supported current lookup metadata, not ambiguity or
   a selected first/last token row. No canonical/publication/validity flag upgrade.
3. Retrieve only the pinned row via fully quoted SQL and bounded JSON projection.
   Parent result uses existing 128 MiB bound; row projection <=64 KiB before Python
   materialization. This bounds returned evidence, not SQL parsing work/time.
4. Check projected ordinal/token/source_fields_hash against the exact native pin.
5. Repeat source lookup and row projection; changed observed evidence blocks output.

native_reference_lookup_verified=True means those native lookup/projection checks
passed. It does NOT mean provenance_verified on the pure descriptor, canonical
identity, complete audit lifecycle/frontier verification, economic validity, availability
or publication. In particular the current native reference reader checks its origin
job scope and latest state; this package does not upgrade that into full attempt/
event coverage. It inherits that existing boundary rather than claiming stronger
verification. Current lookup is not as-recorded historical replay or an atomic
Bronze/Silver snapshot. Matching observations cannot rule out transient drift.
SQL/source failures propagate; no fabricated business rejection or silent fallback.

## CLI

    uv run python scripts/inspect/describe_native_derivative.py `
        --bronze-db <existing-bronze> --reference-db <existing-native-reference> `
        --assessment-id <exact-pin> --instrument-token <token>

Default is no-I/O planning. Add --describe for existing inputs opened read-only.
No raw/frozen source row in CLI output; exceptions are redacted. Exit 0 means a
syntactically supported described observation, NOT canonical identity or permission.
Exit 2 means blocked/unsupported/unresolved/inconsistent (or argument error), exit 1
is DERIVATIVE_DESCRIPTION_FAILED. No execute/initialize/force/network modes.

## Remaining identity gates and acceptance

This package is the source-linked description prerequisite, not completion of
canonical identity. Next substantive work needs independently evidenced canonical
underlying identifiers, explicit audited row-to-contract binding assessments,
conflict/invalidation resolution before selection, immutable history, verified
consumption and temporal claims kept separate. Provider labels/hashes alone cannot
supply those assertions. Positive decision admission remains unavailable under the
research-only publication contract.

No data loading, migration, live acquisition, backfill, audit repair, publication,
strategy execution or decision-loop cutover. Build/test with synthetic fixtures;
package QA does not establish full-platform acceptance. See QA_REPORT.md.
