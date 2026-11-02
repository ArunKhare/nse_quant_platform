# Current-source revalidation of archived research-IV builds @1

## Reconciliation

Latest USER-REPORTED committed QA-passed baseline dd9351c, HEAD and origin on
feat/medallion-feature-store. Assistant has no repository/branch/HEAD write access
or independent actual-repository QA. Updated actual uploaded research_iv_store.py,
research_iv_record.py, native_research_option.py and store boundary fixture were
returned and inspected. Current archive/native signatures and flags reconciled.
No existing file is replaced; preserve all committed QA corrections, assertions,
solver bounds, actual pyproject Python>=3.12/SciPy>=1.14 and data-model boundaries.
If a target addition exists, STOP and compare rather than overwrite.

## New gate

Archive verification alone does not establish CURRENT source consistency. New API:

    revalidate_research_iv_build(
        bronze, frame_silver, reference_silver, assessments, source_gold, archive,
        build_id_pin=..., expected_archive_fingerprint=...,
    )

Caller supplies exact reviewed retained-head pin AND whole archive fingerprint.
No terms/result/source-role DTO accepted. Service reconstructs exact original
ScenarioTerms, option/spot build pins and scenario pin from actual verified archived
bytes. It does NOT infer a new scenario, choose latest builds or substitute sources.

Sequence:
1. Check supported dependency versions/pins and archive/source same-file separation.
2. Actual read_research_iv_archive, including full scoped history, original job,
   dataset contract, definition and definition origin in its OWN scope.
3. Require exact reviewed archive fingerprint, retained head and stored positive
   research candidate. A newer review head or older good pin stops BEFORE pricing.
4. Parse exact stored terms through ACTUAL ScenarioTerms and verify scenario/build
   identity. No caller assumption substitution or arbitrary encoded result import.
5. Actual native Gold-consuming builder twice, each re-reading both pinned roles.
6. Compare canonical complete current DTO bytes to ORIGINAL stored result bytes,
   and first/second current DTO bytes to each other. Exact, no rounding/tolerance.
7. Actual complete archive read again; require full DTO/history fingerprint equality.

Both returned fresh observations are retained, including first-good/second-bad or
stable newly-bad results. No earlier/later good fallback. Store audit review failures
before/after use fixed redacted reasons; after-failure preserves the completed fresh
observations but grants no match. SQL/input/native errors otherwise propagate, never
fabricate business rejection or success. No repair/record/new audit job is performed.

Strict exact equality is intentional: source audit changes, model/solver output,
Python/SciPy numerical-context changes or decimal-input representation can require
explicit new audited reassessment even if displayed IV/Greeks look similar. No
fuzzy equality, rounded result acceptance or comparison of IV alone.

Positive matched_current_research_iv sets archived_recording_verified,
current_source_checked, exact_recording_reproduced and archive_unchanged_observed.
It means sequential observed consistency under exact EXISTING native profiles,
not globally freshest market data, provider authenticity or stronger source-origin
assurances than those native readers actually implement. Original unknown event
clocks stay None; no publication/economic/availability time is filled.

No authoritative scenario/identity/option-underlying binding, publication,
historical validity, availability, canonical contract or decision eligibility.
These flags remain False/None. No atomic cross-database snapshot claim, proof
against change-and-revert or future continued validity. Not whole-platform exact
replay or user-data loading acceptance. Older archive/source APIs remain unchanged.

## Inspection CLI: genuine no-I/O default

    uv run python scripts/inspect/inspect_research_iv_build.py `
      --bronze-db <existing> --frame-silver-db <existing> `
      --reference-silver-db <existing> --assessment-db <existing> `
      --source-gold-db <existing> --archive-db <existing> `
      --build-id-pin <exact-pin> --archive-fingerprint <reviewed-fingerprint>

Default prints PLANNED with provided path TEXT and false verification flags. NO
resolve/exists/is_file/stat/samefile/open, native execution/duckdb imports, DB opens,
initialization, writes, network or credential reads. All path work happens ONLY
with --execute. The service never opens paths itself; owned connections required.

--execute requires all SIX files already present, archive distinct from all sources,
opens EVERYTHING read_only=True, and reuses one handle for same-file source aliases.
No new DB or filename creation, no second independent live-file ATTACH.
It prints only fixed reasons, pins, fingerprints and boolean evidence flags; never
stored/current payloads, plans or arbitrary exception bodies. Execution exceptions
emit fixed RESEARCH_IV_REVALIDATION_FAILED. Exit0 for plan or exact matched execution;
exit1 for review/failure; argument errors exit2. No live acquisition/ingestion.

The archived fingerprint is an explicit caller-reviewed expectation, not authority.
Obtain it from actual read_research_iv_archive and review it independently; this CLI
will NOT auto-fill it from latest state. Review of a pin is not authenticated trust.
No production execution was performed during delivery.

## Tests / verification attribution

19 sandbox tests passed: 18 PURE exact observation/bounds tests and one default-CLI
no-I/O/import-guard test. This is NOT native archive/source/math or full E2E QA.
No reconstructed source dependency/harness, no fake successful native computation.

Twelve boundary integration cases supplied, NOT executed by assistant. They invoke
actual archive/AuditLedger/native model/Gold SQL reader via existing fixtures whose
LOWER SOURCE KERNEL IS SUBSTITUTED. Explicitly NOT full native acquisition-to-IV E2E.
Cover exact match/no writes/unknown clocks, source invalidation, superseded or stored
review pins stopping before pricing, exact archive retry drift, earlier-good/later-bad,
incomplete audit before/after, reviewed history pin, read-only archive, native error
propagation and distinct cursor/same-file rejection with usable parent.

Native and CLI --execute integration/full repository QA, supported SciPy runtime
execution, Ruff, mypy and Windows PowerShell NOT run here. All Python syntax,
line lengths/trailing whitespace checked. ZIP nonempty/CRC/exact ten-member set,
nine payload SHA256s and archive checksum verified. No skips, broad ignores,
replicated native dependencies or weakened assertions/thresholds.

## Apply / QA

Review and copy ABSENT additions only; preserve unrelated runtime logs. Then:

    .\scripts\qa\qa_research_iv_revalidation.ps1

Runner verifies expected branch/dd9351c ancestry, actual HEAD/parents/status and
Python/SciPy/dependency version, focused tests then ALL mandatory QA, fail-fast:

    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Untracked whitespace checked separately; git diff --check does not cover untracked
files. No staging/commit. Suggested commit ONLY after actual passing local QA:
feat(data-platform): revalidate archived research IV against current native sources

No actual source acquisition/loading/migration/backfill, identities/governance
registrations, publication/trading/decision cutover. Synthetic disposable tests only.
Data-loading hold unchanged. Remaining separate gates include audited analytics
bundles, authoritative source-role/identity/time evidence, eligible publication and
native strategy/decision/exact replay plus operational platform acceptance.
