# Native Gold quote storage @1

## Scope
Implements audited persistence of provider-packet-price-fields@1 candidates in a
separate dedicated Gold DuckDB. Store version gold-provider-price-builds@1;
command build.provider_quote_prices@1. Data loading/migration remains on hold.
This is not a Gold reader, publication, immutable feature bundle or decision path.

## Objects and identities
- gold.quote_price_schema_versions: schema version 1.
- gold.quote_price_definitions: immutable per feature_version. Exact retries
  require the same canonical definition bytes and definition fingerprint.
- gold.quote_price_builds: immutable full GoldQuoteCandidate JSON, exact build_id,
  source assessment/evidence lineage, versions, outcome, temporal fields, links,
  recorded_at and first_job_id. Blocked outcomes are preserved too.
- gold.quote_price_build_attempts: one link per committed execution job to build_id.

All Gold object SQL uses quoted catalog.schema.object names, including catalogs
named gold or containing quote characters. Audit APIs remain unchanged.
The registered Gold dataset contract uses VERSIONED_BUILDS with required
build_id,event_ts,published_at,feature_version. Unknown event_ts is NULL, not a
receipt/normalization timestamp. published_at/effective endpoints are always NULL.

Input revision = SHA256(canonical([assessment_revision_id,
    [STORE_VERSION, FEATURE_VERSION, DEFINITION_FINGERPRINT]])).
Build identity is the kernel's exact content-addressed candidate build_id,
recomputed from canonical candidate JSON with build_id="" before accepting it.
Definition identity is independently recomputed before any initialization.

A fresh kernel execution occurs inside every audited attempt. There is no
arbitrary precomputed-result import API. No input DBs are written. Output must
be separate from every input connection/file, including attached DB paths.
Only gold/medallion_audit tables are permitted in the output catalog; legacy
operational DBs and Silver/Bronze output reuse are rejected before audit writes.

## Atomicity, retries and invalidation history
Definition insert, build insert and attempt link commit in one domain transaction.
Exact retries reuse the build and definition and append a new audit job/attempt.
Changed evidence appends a build linking all bounded prior builds for the same
input identity; statuses are not filtered. No UPDATE or DELETE is issued.
Exact older-result reuse after a newer build DOES NOT revive the old build.
History links stay unchanged. A future consumer must resolve invalidation first,
not pick latest/old-good/candidate-only/success-only rows.

Audit planning/RUNNING/terminal events are independent of domain commit, following
AuditLedger. A committed build or attempt link is not proof of audit success.
Final-audit failure propagates and preserves real committed evidence. Fresh retry
gets a new job; it does not repair an earlier job or rewrite first_job_id.
Do not consume builds until the next verified Gold consumer exists. It must
validate definitions, content, history, attempt audits and current source evidence.
Incomplete audit jobs require reviewed handling, never automatic success.

## Bounds and trust
Definition <=32768 UTF-8 bytes; candidate JSON <=1 MiB; new builds may link at most
1000 prior builds for one input. Exact retries remain allowed at the history bound.
Attempts/audit remain append-only and can grow. One owner per writable connection;
no external transactions/concurrent writers. Inputs use their existing independent
read snapshots, not a cross-database atomic lock or publication barrier.
Build timestamps are recording metadata, not provider/publication/economic clocks.
No claim of hard wall-clock network limit, provider truth or raw wire capture.

## Execution CLI
Default plan opens no databases, imports no execution service, does no network,
credential lookup, initialization or source data migration.
--execute requires actor/code revision and four existing input databases.
New output needs explicit --initialize; parent directory must already exist.
Frame/reference Silver aliases reuse one read-only input connection. All output
aliases with inputs are rejected. Caller should use trusted local paths; path
checks are not protection against hostile concurrent filesystem replacement.

CLI execution exit 0 means assessment build execution committed, INCLUDING a
blocked domain result. It does not mean usable/published/eligible data. Read
execution_status, status, reason_code and the explicit false publication/eligibility
fields separately. Exit 1 is bounded generic GOLD_QUOTE_BUILD_FAILED; argparse
input errors use exit 2. Exception text and raw feature payloads are not printed.

## Next acceptance stages
Verified native Gold consumption, immutable bundles/publication, temporal admission,
native decisions and exact replay remain separate gates. The existing completion
checklist is not modified or marked complete by this package. No user data loading
or legacy migration is authorized by storing these builds.
