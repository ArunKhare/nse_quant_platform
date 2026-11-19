# IV-collapse runtime evidence package

This is an additive diagnostic patch, NOT a fix or QA closure.

The uploaded position-monitoring test already contains the two-state premium drop
and local instrument alignment. The uploaded production ExitEngine uses non-null
ATM IV and iv_rank < iv_collapse_pct, not entry/current-IV decay. The decision-loop
and IV-rank builder sources were not returned by source inspection, so their
history requirements and persistence ordering remain unresolved.

## Apply safely

Extract outside the repository. Review the three payload files before copying.
Copy only absent files at their matching relative paths; if any already exists,
stop and compare locally. Do not overwrite files or apply stale snapshots.
No existing production file, shared fixture or exact exit assertion is changed.
Run the supplied PowerShell script from the actual repository with uv installed.
The script verifies the branch, prints HEAD/status/runtime and source hashes,
then runs the focused test with the plugin and every mandatory QA command.
It stops on the first failure: subsequent commands are NOT reported as passed.
It does not stage, commit, push, acquire, migrate, publish or trade.

## Runtime observation

The explicitly loaded pytest plugin uses current-thread Python profiling and
observes returns from the actual native ExitEngine.evaluate. It never replaces
that method or changes features, thresholds, evaluation results or assertions.
It refuses to replace an existing profiler and removes its profiler in teardown.
Its report section contains only allowlisted numeric inputs and enum reason values;
no exception bodies, credentials, raw source payloads or arbitrary details.
Run with -rA to retain report sections on both passed and failed tests.
An evaluation count of zero is missing evidence, not a successful exit.
Threaded evaluation is outside this probe's coverage.

The report identifies null ATM IV/rank, a failed strict threshold predicate, or
competing selected reasons. It deliberately does not invent entry IV: that value
is not consumed by the inspected exit calculation. Obtain the actual feature
builder/history lookup, loop enrichment/monitoring order and position persistence
sources before changing production semantics or seeding historical observations.

## Verification limitations

Sandbox: three pure projection tests only. These are not native integration or
full end-to-end tests. Syntax/archive/member/checksum checks are separate.
No actual repository tests, Ruff, mypy, git diff --check or PowerShell execution
were performed by the assistant. Python >=3.12 from uploaded pyproject is unchanged.
Last user-reported commit remains 0646140; no newer commit has been verified.

Return actual HEAD/status, any newer traceback and the iv-collapse-observations
section. Do not advance identity/eligibility acceptance or load user data on the
basis of this diagnostic package.
