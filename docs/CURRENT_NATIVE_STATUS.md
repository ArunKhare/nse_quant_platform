# Current native-platform status

Status reconciliation: 2026-11-04. This document separates source inspection,
user-confirmed repository QA and supplied Git history. It is not an independent
inspection of the local Windows repository or an authority to release held work.

## Evidence basis

The user confirms that Sources represent the latest committed implementation and
that repository QA/tests passed, including the latest native-input package.
That confirmation is accepted; it is not assistant-reproduced repository QA.

Reported HEAD: 6cf241974a5825bedd85e5da0cfbfe8dcfc2eaa5 on
feat/medallion-feature-store. Later confirmation says changes are committed but
provides no newer exact hash. The native-input package's exact commit association
has not been established; do not assign it to the reported HEAD by inference.

Reported commits:
- 7ea548cba546da2fe6d7f2d2f79f9f6605fbc981: signed publication temporal evidence.
- 78272d0d522d7385776405423e30f392ff8ac050: observed governance key lifecycle.
- f5d9bd5e4ed3ed591b0762a5fed53a10a42d0730: native failure acceptance coverage.
- 3c260114c5be9f81395b8e0cd2dc4726f41b22ab: fixture lifecycle/frame-format repair.
- 37733d7: joint delta-gamma-vega stress attribution; only a short hash supplied.

Last supplied worktree observation listed one worktree and only
logs/live_status.json modified. This is historical user evidence, not a current
clean-worktree claim. Preserve that runtime log.

## Native architecture and existing boundaries

Received artifacts -> immutable Bronze -> typed source-linked Silver -> versioned
Gold -> published bundles -> native decisions and exact replay.

Legacy option_stream mixes observations and analytics; it is not native Bronze.
Provider tokens, symbols, labels and self-hashes are not canonical identities.
Unknown provenance and source times remain unknown. Build native services rather
than extending transitional legacy adapters.

Inspected source contracts include:
- native_strategy_requirements.py: direct iron-condor proposal inventory only,
  not complete strategy, portfolio-risk or decision-loop readiness.
- native_refusal_service.py: two actual admission observations, after early
  safety checks; full encoded observations retained for the refusal kernel.
- native_refusal_decision.py: refusal-only @1; strategy/risk/execution NOT_RUN;
  complete original pre-strategy refusal replay, not complete strategy replay.
- native_refusal_store.py: dedicated first-write recording, exact decision and
  recording pins, original audit obligations, separate domain/final-audit commits.
- native_publication_temporal.py: actual lifecycle/publication integration while
  reproducing existing research admission refusal; no independent time truth.
- kite_decoder.py: both binary and kite_ws_binary_payload are accepted; ordered
  depth tuples are preserved without inferred authoritative bid/ask semantics.

## Accepted native-input package

User-confirmed implemented, QA/test-passed and committed. Delivery scope reported:
exact-price/depth DTOs and codecs, bounded supplied-subset validation, assembly
through actual native readers with repeated full-context checks, fourteen pure
DTO/codec tests and eight supplied native integration cases using real disposable
Bronze -> Silver -> Gold producers. The later user QA confirmation is accepted;
no separate per-case assistant execution result is inferred from it.

The package preserves decoder-order depth, absent OI/volume versus zero and each
option's exchange/last-trade times without synthesizing a chain timestamp. It does
not select latest-good quotes, infer canonical identity or grant decision admission.

Its actual source paths/interfaces were not recovered by the retrieval tool in
this session. That is a retrieval limitation, not evidence of absent/stale code.
Do not replace it with requirements-only, price-only bundle or older research-IV
services. Inspect its current interfaces before choosing implementation changes.

## Remaining gates

1. Independently authenticated governance/namespace authority and real lifecycle
   evidence, not merely possession of a supplied signing key/root.
2. Authoritative underlying identity, derivative binding and authorized revocation.
3. Independently evidenced availability and economic validity; knowledge_cutoff
   and economic_at remain separate axes.
4. A NEW sufficient eligible publication/admission contract. Existing research
   @1 must still reject POINT_IN_TIME_DECISION; candidates do not promote it.
5. Research lifecycle/recovery beyond bounded first-write profiles without healing
   original failed, incomplete, unlinked or orphan obligations by later success.
6. Complete required native strategy/analytics inputs, actual audited native
   strategy/risk decisions and complete exact replay of stages that actually run.
   Reconcile uncovered inputs against the accepted current candidate first.
7. Full integrated and operational acceptance. Package QA is not platform acceptance.

No new failure is reported. Do not reopen historical closed regressions, invent a
completion percentage or interpret legacy 'no blockers' as native admission readiness.

## Holds and operational policy

Data loading/migration remains held. No live acquisition, user-data migration or
backfill, real identity/key/policy/authority registration, production publication,
trading or decision-loop cutover is authorized. Disposable synthetic fixtures are
allowed. No allow-unknown, force-eligible or caller verification boolean bypass.

scripts/qa was intentionally deleted by the user. Do not recreate it or rely on
historical runner references. Run QA commands directly when repository execution
is available, checking the actual uv-selected interpreter rather than prompt labels:

    uv run python -c "import sys; print(sys.executable); print(sys.version)"
    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Check untracked additions for whitespace separately; git diff --check does not
cover them. Do not auto-stage, clean, discard or delete runtime logs.

Inspected pyproject.toml: project version 0.4.0, Python >=3.12, SciPy >=1.14.0,
cryptography >=46.0.0 and DuckDB >=1.1.0. Ruff targets py312, line length 100,
rules E/F/I/B/UP/SIM. Mypy covers src/, scripts/, tests/ with untyped-definition
checks and warnings for unused ignores/redundant casts. These are configuration
requirements, not evidence of an installed interpreter or successful current QA.

## Verification attribution

- User-confirmed repository QA: accepted, including the native-input package.
- Supplied Git history: retained above, not independently verified locally.
- Historical assistant sandbox checks: keep original attribution and scope.
- This documentation delivery: text/patch/archive checks only; no repository
  execution, native integration, pytest, Ruff, mypy, uv or local Git verification.

Historical delivery records remain useful, but their then-current baseline,
'unconfirmed' temporal status and runner instructions are not current policy.
