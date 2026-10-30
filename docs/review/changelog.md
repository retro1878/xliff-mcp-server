# Changelog

Every change made to this fork for the Smartcat fill-target work, in order, with the reason. Commits are on `main` (the fork's default branch); `git log --oneline` is the authoritative sequence.

## Step 1 — review only, no server code changed

### 2026-10-30 — repository brought in, fixtures measured, review trail created

- **Files added**: `docs/review/findings.md`, `docs/review/changelog.md`, `docs/review/tests.md`, `docs/review/open-questions.md`, `CLAUDE.md`.
- **Files changed**: `AGENTS.md` (added a pointer to `docs/review/` at the top).
- **Reason**: the task requires a review trail that stands alone, and `AGENTS.md` is the file every agent reads first; `CLAUDE.md` was absent from the fork.
- **Server behaviour changed**: none.

### Note on `tests/fixtures/`

`tests/fixtures/` did not exist in the fork (`dd909e0`). The real Smartcat export supplied for this task was copied to `tests/fixtures/smartcat-acra-en-ar.xliff` on disk during Step 1 **but is not part of the Step 1 commit**; whether it may be committed is open (`open-questions.md`, Q2). No other fixture was invented in Step 1 — `tests/samples.py` already contains a plain XLIFF 1.2 and an SDLXLIFF sample, and reusing them is the smaller change.

## Step 2 — tests first (red)

### 2026-10-30 — invariant tests and fixtures, no server code changed

- **Files added**: `tests/test_fill_invariants.py`, `tests/fixtures/plain-en-ar.xliff`, `tests/fixtures/plain-en-fa.xliff`, `tests/fixtures/smartcat-en-ar.xliff`, `tests/fixtures/README.md`.
- **Files removed**: `tests/fixtures/smartcat-acra-en-ar.xliff` (the real export copied in Step 1; never committed). Replaced by the anonymised derivation after Q2 was answered.
- **Files changed**: `docs/review/{tests,changelog,open-questions}.md`.
- **Reason**: the task requires tests that fail before the fix. The suite is deliberately red: `10 failed, 27 passed`.
- **Server behaviour changed**: none.
- **Scope decision (Q1)**: SDLXLIFF is out of scope; `.xliff` only.
