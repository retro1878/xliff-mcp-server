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
