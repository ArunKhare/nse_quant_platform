FS2a reconstructed ZIP delivery

This bundle reconstructs the implementation previously shown in this conversation.
It is not a byte-for-byte recovery of the previous unavailable archive.

Contains fs2a.patch, Apply-FS2a.ps1, and source/ for direct review.
Apply only via the reviewed patch; do not manually overwrite existing source files.
The PowerShell script verifies branch, clean worktree and patch applicability.
See source/docs/operations/fs2a_application.md for application and QA commands.

Validation in this turn: 25 decoder/plan tests passed on Python 3.12; all modules
compiled; git apply --check passed in a disposable empty repository.
Two real-project integration tests supplied but NOT executed. Full repository QA,
Ruff, mypy, Python 3.14.2 and Windows script execution NOT tested.
No live-market tests; no user files applied or committed; no branch verified locally.
