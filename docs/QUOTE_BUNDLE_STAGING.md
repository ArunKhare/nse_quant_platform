# Audited quote-bundle staging @1

## Scope
stage_quote_bundle(bronze, frame_silver, reference_silver, assessments, gold, staging,
    build_ids=(<explicit pins>, ...), artifact_root=Path(...), actor_id=...,
    code_revision=..., initialize=False)

Five caller-owned read-only inputs, separate single-owner FILE-BACKED staging DB,
no enclosing transactions. Frame/reference Silver may share. No public arbitrary
bundle-import/adoption API: stage always freshly invokes two-pass source assembly.
Output cannot be a legacy DB or another native Gold data store. Only its three
staging Gold tables plus the audit namespace are allowed. Artifacts have a trusted,
dedicated root outside database paths. The staging DB binds that resolved root
immutably; changing it is not a silent relocation or migration.

## Objects / contract
- gold.quote_bundle_stage_schema: version 1, canonical artifact-root binding.
- gold.quote_bundle_stages: build_id=bundle SHA256, input scope, version metadata,
  membership/hash/byte/member counts, artifact name, SEALED_NOT_PUBLISHED state,
  bounded prior-stage links, unknown event/publication times, recorded_at and job.
- gold.quote_bundle_stage_attempts: one job/build link per committed attempt.
Gold contract: VERSIONED_BUILDS, required build_id/event_ts/published_at/feature_version.
feature_version is quote-feature-bundle@1; there is no single inferred bundle event
time. event_ts and published_at remain NULL. recorded_at is local metadata only.
All owned domain SQL uses fully quoted catalog.schema.object names.

Version quote-bundle-staging@1; command stage.quote_feature_bundle@1.
Input scope = SHA256(canonical([[staging version,bundle version], sorted build pins])).
Config hash additionally binds the resolved artifact root. Bundle identity stays
exact SHA256 of canonical manifest bytes, not the stage scope or job ID.

## Fsync-backed no-replace artifacts
BundleArtifacts validates exact bundle bytes with the committed codec, writes a
private same-directory temporary file, flushes/fsyncs the file, then hard-links
into the content-addressed final name. No overwrite/rename/copy fallback exists.
The successful link provides atomic visibility of complete file bytes, NOT a
cross-resource transaction or an end-to-end power-loss durability guarantee.
There is no directory-fsync guarantee. Filesystem hard-link support is required.
Temporary files owned by this attempt are cleaned in its normal finally path;
crash remnants are not scanned, resealed or deleted on startup. Final artifacts
are never automatically deleted, truncated or overwritten. Symlink targets reject.
Existing artifact reads request at most MAX_BUNDLE_BYTES+1 before validation.
ManifestStore is not modified or used for its unbounded existing-file read path.

## Commit boundaries / recovery semantics
1. Audit plan and RUNNING commit independently.
2. Freshly assemble every requested member; rejection never writes a manifest.
3. Check exact retry metadata/history bounds before file creation.
4. Write and re-read/verify complete manifest bytes.
5. Atomically commit immutable stage metadata and attempt link in one DB transaction.
6. Audit terminal success is a separate event after domain commit.

- Artifact absent + no stage row: new staging may proceed.
- Valid artifact + exact existing row: fresh source verification; append attempt only.
- Artifact present + no row: orphan, REVIEW REQUIRED; no silent adoption even if valid.
- Existing row + missing artifact: REVIEW REQUIRED; no automatic reseal/recreation.
- Corrupt/conflicting artifact or metadata: fail and preserve evidence, no overwrite.
- Domain failure after linking: file remains an orphan; metadata rolls back and
  audit fails. A normal retry refuses to adopt the orphan; reviewed recovery is
  a future explicit operation, not an automatic fallback.
- Final audit failure: real committed file/row/link remain, job may stay RUNNING.
  Retry gets a new job but does not rewrite first_job_id or manufacture old success.
  A later successful retry does not erase the earlier incomplete audit obligation.
- A missing archive root with existing stage rows blocks rather than creating a
  new archive and hiding root loss. Per-artifact checks concern the requested
  bundle, not an unbounded global health scan of all historical files.

No AuditLedger PUBLISHED event is emitted. This operation uses RUNNING -> SUCCEEDED
for successful staging, not the ledger's staged/validated/publication workflow.
SEALED_NOT_PUBLISHED is artifact metadata, not domain publication authority.

## History and limits
New content for the same explicit pins retains both manifests and links all at
most 1000 prior committed stage IDs. Exact retries preserve history/first job and
append attempts. Reusing an exact old snapshot does not revive it or rewrite
supersession edges. No latest/old-good selection API exists in this package.
Membership and byte bounds come from quote-feature-bundle@1 (64 members/4 MiB total).
Stage metadata contains no raw payload or arbitrary exception strings; audit
failure reasons stay bounded. Attempt/audit history grows append-only.

## CLI and trust boundary
Default plan opens/creates no DBs, directories or artifacts and imports no execution
service. --execute needs code revision, actor and existing inputs. New staging DB
requires --initialize. Its parent must exist; the artifact root can be created
only during successful new artifact writing. Input roles/file aliases/root conflicts
reject. Execution inputs are read-only. Errors produce only BUNDLE_STAGE_FAILED.
Exit 0 means staging committed, NOT published or eligible; input errors use exit 2,
execution errors exit 1. No --publish, --repair, --adopt or network option exists.

Use trusted local paths/single-owner access: checksum and alias checks are not
signatures, DB permissions, malicious filesystem-race protection or immutability
against another process with write privileges. Revalidation is sequential, not
an atomic cross-database information frontier. Source changes after final reads
remain possible. No full capture-health/provider-truth/exact-replay guarantee.

## Completion boundary
Next is a verified staging consumer and reviewed recovery planning, then separately
authorized publication/temporal admission. Staged bytes/metadata alone are not a
trusted published bundle. Data loading/migration remains deferred. No legacy data,
receipt/publication time, IV/Greeks or contract identity is relabelled or invented.
