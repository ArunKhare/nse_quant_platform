# Nonexecuting recovery review inventory of research-IV artifact roots

## Actual baseline and source access limitation

User reports 9fffc70 at HEAD and origin/feat/medallion-feature-store, QA/tests passed.
This accepts the first-write stage package as user-reported committed/pushed local
baseline. No newer failure is invented. This new inventory candidate is uncommitted.

Targeted source retrieval did NOT return the new stage implementation, record codec
or stage boundary fixture, and one retrieval failed. Returned snapshots instead
contain inspected artifact_files@1, native materializer and current bundle service.
No repository/file connector was available. Therefore current-stage consumption
was NOT implemented by reconstructing a stale generated stage package. No claim
is made that actual 9fffc70 stage sources were inspected or reconciled.

Selected independent bounded slice: safely enumerate artifact recovery-review
conditions against the INSPECTED research-iv-artifact-files@1 contract. This fills
an operational gap: ordinary artifact read/write refuses roots containing pending
or foreign entries, while operators must be able to OBSERVE them without cleanup.
It does not query a stage database, determine ownership, classify true orphans,
prove native math, authorize recovery or grant publication/admission.

All nine payloads are additive; do not overwrite existing local/committed files.
Direct repository writes, staging, commit and push were unavailable/not performed.
Existing stage, materializer, artifact and inspection sources remain untouched.

## APIs and bounded output

- research-iv-artifact-recovery-inventory@1
- inventory_research_iv_artifacts(absolute_root_path)
- scripts/inspect/inspect_research_iv_artifact_inventory.py
- python -m nse_quant.data_platform.research_iv_inventory_cli

The CLI defaults to PLANNED, echoes the supplied root string and performs no path
probes, resolving, file opens, directory scans, execution implementation imports,
network or credential lookup. Plan root text is bounded to 2048 noncontrol characters.
No existing-root or absolute-path claim is inferred from a default plan.

Example safe nonexecuting plan:

```powershell
uv run python scripts/inspect/inspect_research_iv_artifact_inventory.py `
  --artifact-root missing-artifact-root
```

Only append --execute with an explicitly chosen absolute existing trusted root to
read it. Execution gates the actual file API version, suffix, 4 MiB file bound and
256-entry limit. No root initialization, file write, delete, truncate, rename,
adoption, automatic retry, source loading or stage-ledger mutation is implemented.

Inventory takes TWO whole bounded passes, retaining both observations. It compares
entry identities/modes/sizes/mtimes, hashes of read artifacts and root identities.
Up to 256 entries (including pending/foreign/nonregular), <=4 MiB per conforming
artifact, and <=16 MiB aggregate conforming-body reads PER pass. A bound failure
raises; no truncated prefix is accepted as a complete observation. CLI output is
bounded to 256 KiB. These are observation/payload bounds, NOT process-memory ceilings.

Only regular nonredirected files with exact `<64-lowercase-hex>.research-iv.json`
names and supported sizes have bodies read. Reads are bounded, check opened inode/
size/mtime, and are never recursive. Root symlinks/junctions are rejected; redirected
entries are reported without following them. No pending or foreign body is read.
Metadata sizes are labeled size_bytes_metadata, not claimed content reads.

## Entry kinds: none is recovery authorization

- PINNED_BYTES_UNASSESSED: file SHA-256 matches filename ONLY. Even arbitrary non-JSON
  bytes can satisfy this; no canonical schema, numeric truth or ownership is granted.
- ARTIFACT_PIN_MISMATCH_REVIEW: observed bytes disagree with filename pin.
- ARTIFACT_SIZE_REVIEW: zero/oversized conforming entry; its body is not read.
- PENDING_REMNANT_REVIEW: pending-prefix regular entry, body NOT read/deleted.
- FOREIGN_ENTRY_REVIEW: unrecognized regular entry, body NOT read/deleted.
- NONREGULAR_ENTRY_REVIEW: directory/other entry, not traversed/opened.
- REDIRECT_REVIEW: symlink/junction entry, not followed/opened.

Only exact safe artifact names appear in output. Other names are represented by
SHA-256 of filesystem-encoded name bytes, with artifact_name=None. This avoids
printing arbitrary filename controls, secrets or raw payloads. Name hashes are
local review references, not authority, reversible labels or stable contract IDs.
Full exception bodies are never emitted by CLI diagnostics.

A stable inventory returns observed_artifact_inventory_not_recovery_authorization.
Even an empty root is ONLY a local observation, not proof of recovery completion.
Entry drift returns review_required with BOTH passes retained. Disappearance,
read/open/root identity errors, invalid roots or exhaustion fail closed; CLI emits
fixed IV_ARTIFACT_INVENTORY_FAILED and no accepted partial result.

Exit 0 means PLANNED or a stable observation (which may contain REVIEW kinds).
Exit 2 means two-pass drift, or parser usage error on stderr. Exit 1 means execution
failure. No exit code is stage eligibility or cleanup permission.

Every result denies destructive_actions_authorized, stage_ownership_checked,
orphan_status_determined, native_sources_checked, canonical_bundle_schema_checked,
publication_asserted and decision_eligibility_asserted. The fingerprint commits to
ordered entries, identity/metadata and both passes; it does not authenticate source
or publisher, nor prove globally latest state or observation after return.

## Limits of the observation boundary

A trusted single-owner controlled directory is required. Preflight and repeated
reads are not an atomic filesystem snapshot, hostile-writer security boundary,
protection against privileged replacement/rollback, global namespace registry or
multi-database coherence. Hardlinked regular file bytes can be observed but external
owners/aliases are NOT determined. This tool cannot say whether a final file was
staged, orphaned, previously failed, eligible, safe to delete or safe to adopt.
A later recovery action needs actual stage/audit evidence and a NEW explicit
reviewed action contract. None is supplied here.

## Local QA / remaining source request

Use scripts/qa/qa_research_iv_inventory.ps1 with -ExpectedHead set to the reviewed
FULL 40-character Git HEAD from git rev-parse HEAD after inspecting branch/status/
diff. It is NOT short 9fffc70, a filename, stage fingerprint or ZIP checksum.
The runner checks actual branch/HEAD/9fffc70 ancestry, file-profile version, payload
hashes, uv's real interpreter and unchanged Python >=3.12/SciPy >=1.14.0/cryptography
>=46.0.0 bounds, focused tests, all mandatory QA, verifier lint and untracked whitespace:

```powershell
uv run pytest tests/data_platform -q
uv run pytest tests -q
uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
uv run mypy
git diff --check
```

No original QA/test/dependency/tolerance/architecture constraint is weakened.
The ZIP verifier takes an archive path and --sha256 with the separately supplied
64-character archive hash. Manifest covers nine payloads excluding itself; full
archive hash covers the complete ZIP including manifest. Hash integrity is not
authenticated publisher provenance. See the separate verification report.

For a next current-stage consumer, actual committed research_iv_first_stage.py,
research_iv_stage_record.py and test_research_iv_first_stage_boundary.py must be
retrieved/uploaded and reconciled. The previous generated text is not substituted
for those sources and no current-stage/native integration claim is made here.

No acquisition, user-data loading/migration/backfill, real authority/key/policy/
identity registration, production publication, trading or cutover is performed.
Existing data-loading holds and remaining native platform gates stay in force.
