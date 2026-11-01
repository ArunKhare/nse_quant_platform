# Purpose-aware admission receipts and deterministic policy replay

## Baseline and inspected interfaces
User baseline 46a9a5e with writer 707ef1d, QA/tests passed and HEAD/origin aligned
by supplied Git log. Local checkout/branch/HEAD cannot be independently inspected.
This turn inspected actual quote_publication_reader.py ResearchPublicationEvidence
DTO/read API, reader tests and writer/docs. Its availability/current-source/
historical-validity/decision flags are explicitly False; no field is upgraded.
The older standalone reference temporal policy was not returned by exploration;
it is not modified or silently substituted. No existing sources/tests overwritten.

## Add only
src/nse_quant/data_platform/publication_admission.py
src/nse_quant/data_platform/publication_admission_cli.py
scripts/inspect/assess_quote_publication_use.py
tests/data_platform/test_publication_admission.py
docs/PUBLICATION_ADMISSION_RECEIPTS.md

## What this package completes
A versioned policy kernel, strict typed two-axis requests, read-only source-bound
assessment, immutable frozen-input/outcome receipts, exact canonical encoding and
deterministic OFFLINE replay of this policy result. Not strategy/trading execution.
Verified archival research may be permitted WITHOUT as-of assertions. Research
publications always reject point-in-time decision requests; missing availability,
economic validity and canonical identity remain unknown. No clock substitution.
Replay is reproducibility, NOT authenticity/authorization or full decision replay.
No files/DB/audit events written, no loading/migration, no unknown-time overrides.

Public APIs:
AdmissionRequest("ARCHIVED_RESEARCH_ANALYSIS")
AdmissionRequest("POINT_IN_TIME_DECISION", knowledge_cutoff, economic_at)
assess_publication_use(publications, publication_id=..., request=...)
encode_admission_receipt(receipt)
replay_admission_receipt(raw, expected_receipt_id=...)

CLI plan (no DB/execution import or side effect):
uv run python scripts/inspect/assess_quote_publication_use.py --publication-db <registry.duckdb> --publication-id <64hex> --use-case ARCHIVED_RESEARCH_ANALYSIS

Append --assess for a read-only assessment summary. Point-in-time requests use
--use-case POINT_IN_TIME_DECISION --knowledge-cutoff <aware-ISO> --economic-at <aware-ISO>.
They remain REJECTED for current research-only inputs. Plan exit 0 is not admission.
See docs/PUBLICATION_ADMISSION_RECEIPTS.md for semantics and limits.

## Apply / mandatory local QA
Inspect git branch --show-current, git log -1 and git status --short in
C:\Projects\nse_quant_platform. Require feat/medallion-feature-store and reconcile
46a9a5e or newer without resetting work. Compare the actual reader/codec interfaces.
Copy only five additions; STOP on existing paths and compare rather than overwrite.
Run verify-local.ps1 from extracted bundle; review untracked files separately from
 git diff. No deps, architecture, typing rules, configs or existing tests weakened.

## Verification disclosure
48 focused tests passed under Python 3.12.8: research vs decision scope, explicit
aware axes, before/after record clocks, timezone identity, unknown-proof rejection,
source contracts, replay without DB/current sources, snapshot drift, strict hashes/
JSON/types/byte limits and CLI no-I/O/read-only/error boundaries.
The new policy/codecs ran directly. Source reader is substituted; sandbox baseline
codec/models used an interface harness, NOT the full repository source pipeline.
Those harness dependencies are NOT delivered. Real tests import committed models/
codec and existing baseline tests remain intact. No full temporal admission,
authenticity, audited persistence or strategy-replay pass is claimed. Full QA,
Ruff and mypy were not run here; local checks mandatory. Python line lengths,
static imports, patch whitespace and ZIP/file hashes were independently checked.

Suggested commit after local QA:
feat(data-platform): add purpose-aware publication admission and policy replay receipts

Next boundary: audited admission/decision-input snapshot persistence and verified
provenance, not automatic promotion of research inputs. Migration remains held.
