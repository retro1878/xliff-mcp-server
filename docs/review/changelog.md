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

## Step 3 — fix what the red tests exposed

### 2026-10-30 — escaping, segment state, whitespace, span-based replacement

All four changes are in `xliff_mcp/xliff_processor.py`; `tests/test_fill_invariants.py` only gained the corrected `tag_skeleton` helper (closing tags were being counted) and one meta-test that dropped a tag from the source instead of the target.

1. **Translations are escaped before they are written** (`_render_fragment`, used by `replace_xliff_targets`).
   - *Why*: a translation containing `&`, `<` or `>` was interpolated raw and produced a document that no longer parses, while the tool reported success (`findings.md` §5.1).
   - *How*: the string is tokenised into text runs and inline tags (`g/bpt/ept/ph/it/mrk/x/bx/ex`, balanced, otherwise the whole string is treated as text). Text runs go through `xml.sax.saxutils.escape`; tag bytes are kept exactly as sent. No new dependency.

2. **Filled targets get `state="translated"`** (`_with_translated_state`).
   - *Why*: the old code copied the existing target opening tag verbatim, so Smartcat segments stayed `needs-translation` (`findings.md` §5.2).
   - *How*: rewrite the existing `state` value in place; add the attribute when absent; collapse the space left before `>`. Every other attribute, including `state-qualifier`, `x-state-qualifier` and `sc:match-quality`, is left alone (open-questions Q3/Q4 defaults).

3. **Whitespace is preserved when `xml:space="preserve"`** (`_extract_element_content`).
   - *Why*: extraction stripped the element's edge whitespace, which the fixture marks as significant (`findings.md` §5.5).
   - *How*: capture the opening tag with the content; strip only when it does not carry `xml:space="preserve"`.

4. **Entity decoding is single-pass** (`html.unescape`, `_decode_html_entities` deleted).
   - *Why*: the sequential `replace()` chain double-decoded `&amp;lt;` into `<` and mapped `&nbsp;` to a plain space.
   - *How*: stdlib `html.unescape`; `&nbsp;` now becomes U+00A0.

5. **Replacement is span-based, and `<target/>` / missing targets are handled** (`replace_xliff_targets` rewritten around a single `UNIT_ELEMENT.sub`).
   - *Why*: the previous loop re-scanned the mutated document for every translation and used `str.replace()` over the whole file (`findings.md` §5.4, §5.6, §5.7). A self-closing `<target/>` was not recognised, and a new target was inserted before `<seg-source>`.
   - *How*: collect `unitId → text` first, rewrite each unit once in a single pass; a self-closing target is replaced as a whole element; when no target exists it is inserted after `</seg-source>` if present, else after `</source>`. Return value `(content, replacements_count)` is unchanged, so `tool_registry.py` needed no edit.

- **Result**: `37 passed` (was `10 failed, 27 passed`).
- **Not changed**: `validate_xliff` semantics, SDLXLIFF handling (out of scope), `pyproject.toml`.
- **Formatting**: the new test file was run through `ruff format`. `xliff_mcp/xliff_processor.py` was **not** whole-file reformatted — `git show HEAD:xliff_mcp/xliff_processor.py | ruff format --check` already fails at HEAD, so formatting it here would rewrite ~200 unrelated lines and bury the fix. `ruff check .` passes.
