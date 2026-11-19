# Native migrated-price research publication

## Scope and release hold

This additive package implements legacy-price-research-publication@1 and
legacy-price-research-admission@1 over the accepted legacy-price-research-bundle@1.
Only disposable synthetic publication is released. Production publication,
real-data loading/migration, identity/key/authority registration, trading and
native decision-loop cutover remain HELD.

allow_research_publication=True is an explicit intent acknowledgement, not an ACL,
proof of synthetic origin, source legitimacy or a production release decision.
Research acceptance is not organizational authorization, market validity or trade
permission. No independently authenticated authority or point-in-time evidence is
introduced. The legacy paper loop is unchanged.

## Native integration and preserved contracts

The producer consumes the actual accepted legacy_market_gold_bundle assembler,
which reads complete pinned Gold and revalidates native Gold/Silver/Bronze. It does
not import an offline artifact or caller-successful evidence DTO as native proof.
All full Silver inputs and Gold outputs from one entire build remain in the bundle,
with exact definition/runtime and complete partition/event/ordinal lineage.

This profile uses actual native AuditLedger/JobState, DatasetContract with
VERSIONED_BUILDS, and quote_publication_reader._lifecycle, _instant and _canonical.
Admission reuses actual AdmissionRequest and its two-axis canonical request codecs.
These inspected private interfaces are integration dependencies; incompatible changes
require review. The quote-specific publication schema, IDs, bundle codecs and
admission @1 are not modified or weakened. No provider scale, provider Bronze
identity, canonical identity or independent clocks are invented for migrated data.

The new versioned profile has dedicated tables in a separate native file. It is
integrated through native audit, contracts, lifecycle, bundle assembly and request
machinery; it is not a claim that the existing quote reader can decode this profile.
No generic cross-profile dispatcher or production registry is added. Existing native
decision/refusal consumers remain unchanged and gain no positive decision lane.

## APIs

- initialize_legacy_publication(empty_file_backed_target)
- publish_legacy_research_bundle(bronze, silver, gold, target, request=...,
  expected_bundle_id=..., actor_id=..., code_revision=..., purpose="RESEARCH_ONLY",
  allow_research_publication=True)
- read_legacy_research_publication(readonly_publications, publication_id=...,
  expected_recording_fingerprint=...)
- revalidate_legacy_research_publication(bronze, silver, gold, readonly_publications,
  publication_id=..., expected_recording_fingerprint=...)
- assess_legacy_publication_use(readonly_publications, publication_id=...,
  expected_recording_fingerprint=..., request=AdmissionRequest(...))
- encode_legacy_admission(receipt)
- replay_legacy_admission(raw, expected_receipt_id=...)

Caller owns all connections. No outer transaction or shared writer is supported.
Initialize an empty dedicated target explicitly; partial initialization is never
adopted. Close writer owners before read-only reopen. Public readers enforce actual
read-only connections. Accepted live-file separation rejects source/target aliases.
No artifact directory, CLI, automatic acquisition or automatic migration is added.
Execution code revision must be a 40-hex label; it is not source-code attestation.

## Publication lifecycle and original obligations

The first-write scope binds publication profile plus Gold build ID. Recording pin,
bundle ID, runtime and actor/revision labels are excluded from that scope, so new
pins cannot heal an original failed attempt. Existing scoped jobs, records or
same-Gold attempts block writes before upstream assembly. Even successful retries
are deliberately disallowed by this bounded first-write profile. Recovery/adoption
is not implemented.

The producer plans/starts audit, performs actual complete assembly, checks its hash
against the reviewed bundle pin, records STAGED, performs another complete actual
assembly, compares bytes, replays content, and records VALIDATED. STAGED denotes an
in-memory verified candidate, not durable quote staging or a filesystem artifact.

Publication record, full manifest and original attempt link commit atomically.
PUBLISHED follows domain commit; SUCCEEDED is the separate final audit transition.
Domain failure rolls back both domain tables but leaves a failed audit obligation.
Post-commit audit failure can leave committed content; the reader blocks it, and
retry cannot adopt it. There is no healing, old-good fallback or subset publication.

The reader checks dedicated schema, exact definition/contract, full bundle replay,
all materialized metadata, source pins, exact original attempt/scoped job coverage,
and the six-phase native publication lifecycle. Extra scoped jobs and orphan links
block acceptance. Complete original clocks/metadata enter a separately reviewed
recording fingerprint. UTC instant normalization preserves fingerprint equality in
non-UTC session timezones. A changed record clock cannot silently use the old pin.
Application audit integrity is not a DB permission boundary or authenticated root.

## Distinct replay and current-source claims

Retained publication read verifies the frozen full bundle and original publication
recording, without consulting current native upstream. Current-native revalidation
additionally invokes actual bundle revalidation against Gold/Silver/Bronze, then
rechecks the pinned publication. It returns the unchanged retained DTO; its
current_source_checked field remains false. Successful invocation supplies the
additional check rather than rewriting archived evidence.

Neither API checks current legacy SQL equality. Changed legacy SQL does not change
already preserved native evidence. Repeated matching observations do not establish
an atomic cross-database snapshot or independent availability/economic validity.
Inherited Gold/bundle @1 exact-runtime replay restrictions remain. Runtime labels
are not authenticated interpreter/build provenance.

The inner bundle still records publication_asserted=False. It is not rewritten:
the outer registry is the research publication evidence. Canonical identity remains
null; independent availability/economic validity and decision eligibility remain
false. No eligibility override, positive decision lane or full strategy replay exists.

## Admission and frozen-summary replay

Native admission invokes the actual pinned retained publication reader twice and
refuses invalid/operational sources or drift. It freezes a bounded metadata summary:
publication/recording/bundle/Gold pins, coverage count, clocks and limitations. It
does not embed another copy of the up-to-140-MB full manifest in the receipt.

ARCHIVED_RESEARCH_ANALYSIS without either time axis can return ACCEPTED_RESEARCH_ONLY.
POINT_IN_TIME_DECISION always returns REJECTED, even if both request axes equal
publication/audit record clocks. The reused request contract requires both
knowledge_cutoff and economic_at for point-in-time requests; naive timestamps are
not silently assigned UTC.

Receipt replay reproduces policy evaluation from that frozen summary only. It does
not authenticate a declared recording fingerprint, reverify full manifest content,
consult current sources or replay strategy/risk/execution. A fabricated internally
consistent summary can reproduce research acceptance offline; that is not native
attestation. Native assessment has no caller-successful-summary import API.
research_analysis_permitted describes this research policy, not external authority.
Decision eligibility and replay authenticity remain false.

## Bounds and SQL transfer

Original Gold/bundle row and per-row/aggregate bounds are unchanged. One complete
Gold build, one scoped publication and one original attempt/job are accepted.

- Complete manifest: 1..140000000 bytes, inherited from accepted bundle @1.
- SQL count/aggregate-byte preflight before BLOB transfer, covering same-Gold and
  same-scope records rather than a selected good publication subset.
- Independent per-manifest CASE guard and <=512-byte request guard.
- Bounded schema inventory and LIMIT overflow detection for jobs/links/events.
- CASE-guarded metadata and <=32768-byte definition/contract transfers.
- Frozen admission input and encoded receipt independently <=32768 bytes.

No automatic paging, limit inflation, partial success or unbounded export exists.
JSON/hex/recomputation materialize multiple copies; peak memory can substantially
exceed manifest size. This is not streaming production publication. The resource
test retains the actual 140000001-byte SQL payload and complete assertion.

## Tests and verification attribution

The ZIP includes 50 parametrized native cases using actual accepted synthetic
legacy -> partition Bronze -> Silver -> migrated Gold -> bundle -> publication
producer/reader/admission fixtures. Tests cover 1001 rows/two partitions, original
scope/audit/orphan obligations, changed pins, upstream failure, native Gold coverage
loss, second-assembly failure, actual SQL rollback, post-domain PUBLISHED/final-audit
failure, metadata/manifest/claim corruption, transfer bounds, aliases and timezones.
These repository-dependent tests have NOT been assistant-executed.

The ZIP includes 25 pure frozen-summary policy cases. They cover exact receipt
replay, corruption, false positive claims, byte bounds, unsupported source summaries,
mandatory point-in-time refusal and offline declaration-versus-attestation limits.

Historical prior-response verification (before this ZIP reconstruction): 25 policy
cases passed under isolated dependency adapters, and 22 SQL/filesystem checks passed
against the new code under substituted bundle/upstream/audit/contract boundaries.
Those were Python 3.12.8 / DuckDB 1.2.2 checks, NOT native E2E, repository execution
or Windows verification. One harness equality assertion compared dynamically
reloaded dataclass types; field comparison corrected the harness, not domain rules.

The earlier session's in-memory payloads did not persist. This deliverable was
rebuilt from the implementation recorded in the conversation; it is not claimed to
be byte-identical to a previously created ZIP (none existed). Current-turn checks
are syntax/line length/trailing whitespace, parametrized-case inventory, and ZIP
nonempty/exact unique members/CRC/payload equality. The historical 25/22 checks were
NOT rerun against this reconstructed archive. Static checks are not Ruff or mypy.

No assistant uv-selected interpreter, Windows, repository worktree/Git, commit/push,
real native pytest, full pytest, Ruff or mypy execution occurred. User-confirmed QA
through 483ad7f is accepted/closed and is separate from these new additions.
Historical delivery-time verification statements do not reopen completed QA.

## Applying and checking additions

Review/copy absent additions only; stop and compare if a destination exists. No
accepted dependency, QA repair, runtime log, scripts/qa, PowerShell runner,
per-payload SHA256 manifest or standalone verifier is included or replaced.

New-work repository verification remains:

    uv run python -c "import sys; print(sys.executable); print(sys.version)"
    uv run pytest tests/data_platform/test_legacy_market_publication_policy.py -q
    uv run pytest tests/data_platform/test_legacy_market_publication_native.py -q
    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Check untracked additions for whitespace too; git diff does not cover them. These
are checks for new work, not a request to reopen prior accepted QA. No package result
establishes whole-platform operational acceptance or releases the production holds.
