# FS2b2 HTTP transfer-framing policy correction

## Scope and version

Capture policy becomes kite-instrument-http@2. This addendum supersedes the previous
capture-policy version declaration, not the original receipt evidence. Command
invocation ingest.kite_instruments_http@1 and metadata schema version 1 remain unchanged:
CLI/storage structure is unchanged; capture acceptance policy is now explicitly v2.
The existing service imports CAPTURE_VERSION and fingerprints it in config_hash, so
new capture metadata/config fingerprints identify v2 without service replacement.

Do not update, relabel, re-normalize or manufacture success for historical v1 Bronze
receipts. Suspect v1 evidence requires separate append-only review/disposition work;
this patch performs no such operation. Fresh acquisition remains a separately reviewed
network action under a new session identity. No production DB or broker request occurs
while applying/testing this patch.

## Defect and correction

The previous check lower().strip() accepted Transfer-Encoding values such as
"chunked " while CPython 3.12's HTTPResponse did not enable chunk decoding. The body
could contain chunk framing yet be labelled a complete entity body. Reproduced using
real stdlib HTTPResponse parsing in memory, not a broker connection.

v2 uses exact case-insensitive comparison of the parsed header value, without stripping
trailing whitespace. This is a conservative acquisition policy; it is not a claim that
all whitespace-bearing headers are forbidden by HTTP specifications. Unsupported
values fail before body consumption with UNSUPPORTED_TRANSFER_ENCODING.

v2 also requires declared chunked transfer to agree with HTTPResponse.chunked being
exactly True. Disagreement in either direction fails before body reads with
TRANSFER_FRAMING_MISMATCH. Dependency decision: this is an explicit runtime assertion
against the stdlib HTTPResponse parser's chunked-mode attribute, not an SDK decoder.
Injected transports must confirm that mode for chunked responses. Missing attributes
are treated as nonchunked, which cannot satisfy a chunked declaration. Runtime changes
must be checked against these tests, including Python 3.14.2 locally.

Normal chunked/case variants preserve content-coded gzip bytes without decompression.
Ordinary Content-Length and close-delimited responses remain supported. No partial-body
salvage, publication inference or new schema. DEFAULT_HTTP_POLICY's singleton remains
unchanged; B008 is not reintroduced. No changes to drain, capture health, FS2b1, Silver,
legacy execution, strategy, eligibility or decision replay paths.

## Validation boundaries

Sandbox tests use a source transcription of the complete module returned by Project
Files, not the user's filesystem. Seventeen new cases ran with real stdlib parsing
and injected connections: the pre-fix snapshot had six expected failures (five behavior
regressions plus version assertion); all seventeen pass after patching. No network.
The full original HTTP suite, real A1/FS1a integration suite, Ruff, mypy, Python 3.14.2,
Windows execution and full repository QA require local execution. No claim that these
were run or that local branch/HEAD was independently verified.

## Application

Apply framing-fix.patch from a clean feat/medallion-feature-store branch. The included
Python helper checks branch/worktree and git apply --check before applying. It avoids
PowerShell unsigned-script execution entirely. Extract the ZIP outside the repository.
Do not copy the test/doc review files first: the patch adds those files itself.
Do not apply after making the same edits manually. Conflicts must fail closed; never
force patch application over newer source or reset committed work to match a bundle.

Run all local QA commands from the project root after applying. Suggested commit:

fix(data-platform): align HTTP transfer capture with parser framing

- reject unsupported transfer encodings without whitespace broadening
- fail closed on declared/parser chunked-mode disagreement
- version capture policy as kite-instrument-http@2
- preserve B008 singleton default and all existing Bronze evidence
- add real-parser offline regression tests and policy addendum
