# Invalidation-aware native Gold consumer

## Baseline and source reconciliation
User baseline b23cf45, all QA/tests passed, local and origin aligned by provided
Git output. Local repository branch/HEAD cannot be independently accessed here.
This turn inspected current gold_quote_store.py schema, versions, definitions,
input/build identities and attempts, and test_gold_quote_store.py including the
committed aware-instant timezone correction. Current reference_supersession.py
was also inspected. A targeted kernel lookup returned the store instead; kernel
model interface is grounded in its imports plus prior user-confirmed delivery.
No existing kernel/store/tests/configuration is overwritten or weakened.

## Add only
src/nse_quant/data_platform/gold_quote_reader.py
tests/data_platform/test_gold_quote_reader.py
docs/GOLD_QUOTE_CONSUMPTION.md

## Public API
read_quote_price_build(bronze, frame_silver, reference_silver, assessments, gold,
    build_id=<exact lowercase SHA256>)

Caller-owned read-only connections, no outer transactions. Gold separate from all
inputs. Returns immutable GoldQuoteEvidence with bounded reason codes, active
build pins, linked successful job IDs and source-recomputed GoldQuoteCandidate.
No new CLI, DB objects, audit events, publication or migration commands.

Checks include invalidation-first complete graph resolution, immutable definition
and contract fingerprints, explicit version support, input/build identity, strict
canonical JSON, selected-build attempt audits, separately scoped definition origin,
UTC-aware event/trade instant comparison, and exact fresh kernel recomputation.
See docs/GOLD_QUOTE_CONSUMPTION.md for strict audit policy and limitations.

verified_current is evidence verification, not automatic feature eligibility.
Nested candidate.status may remain blocked. All outer publication/validity/
eligibility assertions remain False. A stale source response blocks rather than
rewrites stored evidence. Old pins never fall back to another build.

## Safe apply / local QA
Inspect git branch --show-current, git log -1 and git status --short in
C:\Projects\nse_quant_platform. Require feat/medallion-feature-store. Reconcile
b23cf45 or newer without resetting work. Compare local model/API definitions.
Copy ONLY the three repository additions; STOP if any destination exists and
compare instead. Preserve the existing timezone-safe test. Run verify-local.ps1
from extracted bundle. Review untracked additions separately from git diff.

## Verification disclosure
44 focused tests passed under Python 3.12.8 using actual DuckDB SQL/read snapshots,
including a file-backed read-only DB named gold, unchanged file checksums, escaped
catalogs and UTC/Asia-Kolkata timestamp/evidence identity equivalence. Cases cover
invalidating failed/unsupported successors, graph errors, definitions/shared origin
scope, audit states and retries, tampering/strict JSON, limits and source drift.
Fixtures use Gold schema-column replicas, not calls to the writer. Candidate
computation is substituted. Sandbox baseline graph code/model interfaces were
materialized from inspected/conversation source with condensed formatting; store
constants replicated. Those harness dependencies are NOT shipped. Tests in the
repository import actual committed modules. This is NOT a writer-to-source chain
integration pass. Full local suites, Ruff and mypy remain mandatory, not run here.
Python <=100-character source lines, patch whitespace and ZIP integrity/hash
checks were performed. No dependency replicas are included in the patch.

Suggested commit after local QA:
feat(data-platform): add invalidation-aware native Gold quote consumer

Next boundary: immutable feature-bundle construction and audited publication,
without treating Gold persistence/current verification as temporal admission.
User data loading/migration remains deferred until platform acceptance.
