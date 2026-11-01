# Verified current Gold quote consumption @1

## API and scope
read_quote_price_build(bronze, frame_silver, reference_silver, assessments, gold,
    build_id=<exact lowercase SHA256>) -> GoldQuoteEvidence

All connections are caller-owned/read-only, without enclosing transactions.
Gold must be separate from every input connection/file (attached paths included).
Frame/reference Silver may share a connection. No initialization, schema writes,
audit transitions, migration, publication or decision eligibility.

## Invalidation before quality
Capture one Gold snapshot containing schema versions, FULL group graph, selected
build, immutable definition, contract and audit evidence. Graph resolution occurs
before any status, supported-version or audit-success filtering. New failed,
blocked or unsupported successor rows invalidate older good rows. Multiple heads,
cycles, duplicate/dangling edges, malformed JSON and resource bounds fail closed.
Explicit old pins block, never silently move to another head or old-good fallback.
Shared graph reasons retain GOLD_ plus their existing assessment-oriented names
(e.g. GOLD_ASSESSMENT_SUPERSEDED); no legacy-workspace adapter is involved.

## Selected build checks
- Gold and audit schema version exactly 1; supported command/store/feature versions.
- Registered Gold contract bytes/fingerprint match the native VERSIONED_BUILDS contract.
- Assessment input identity recomputes from pinned source and exact version/config.
- Canonical definition bytes/fingerprint match current supported code, not only DB claims.
- Selected build JSON is bounded, duplicate-key/nonfinite rejecting and canonical.
- build_id recomputes from JSON with build_id=""; duplicated DB metadata agrees.
- Publication/effective interval claims remain NULL and eligibility remains False.
- SQL event/trade timestamps agree as UTC instants with canonical JSON times.
  Returned TIMESTAMPTZ labels in a non-UTC session are not compared as local strings.
- Fresh source-verifying Gold kernel output exactly equals stored result JSON.

## Attempt audits and definition origin
All linked attempts of the selected active build must be correctly scoped and
terminal. At least one must be SUCCEEDED. Terminal FAILED/CANCELLED attempts are
retained but not counted as success; a pending linked retry blocks even after a
successful earlier attempt. first_job_id must have a selected-build attempt link.

The immutable definition can originate from ANOTHER input/build. Its first_job_id
must link to a build of the same definition/feature/store versions. Its input
identity and audit scope are checked against that origin's assessment, not against
the currently selected build. Its origin job must be SUCCEEDED. This verifies the
metadata/definition registration origin, NOT that origin build's current data
eligibility or current source state. Definition bytes also match local code.

An incomplete/failed definition-origin job is NOT repaired or replaced by a later
successful job. The consumer blocks conservatively; reviewed recovery is separate.
No writes or fabricated audit success occur. Jobs with no committed build-attempt
link do not provide authority. Superseded builds' audit status never filters graph
invalidation edges. This is an application evidence API, not a DB permission boundary
or a cryptographic authenticity claim.

## Output and temporal limits
status=verified_current means persisted evidence equals current recomputation.
The nested candidate may itself have status=blocked and no features. Verification
of that disposition is NOT a usable price, publication, historical validity or
eligibility. Inspect both statuses. Outer assertion flags always remain False.
Expected evidence failures return blocked without candidate data. Invalid pins
raise ValueError; SQL/catalog/connection/source execution failures propagate.

Evidence fingerprint covers reader/build IDs, active graph head, definition/origin,
linked attempt audit snapshot and current canonical result. New retry attempts can
change it without changing build_id. No wall clock is added by the reader.
Gold and source snapshots are separate, not an atomic cross-database lock,
publication barrier or historical as-recorded replay. Changes after reads remain
possible. Replay will require immutable published snapshots, not current lookup.

## Bounds
At most 1001 history nodes, 1000 graph links/node (shared resolver), 100000 bytes
per links JSON, 1000 active-build attempts, 32768 definition bytes and 1 MiB result
JSON. Gold queries use fully quoted catalog.schema.object names. Missing/broken
objects can raise operational errors rather than being initialized or repaired.

## Completion boundary
Verified Gold consumption only. Immutable bundles/publication, temporal admission,
native decisions, exact replay and reviewed recovery remain further gates.
No user data loading or legacy migration is authorized by this package.
