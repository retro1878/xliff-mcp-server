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

## Step 4 — diff report

### 2026-10-30 — report every replacement run

- **Files changed**: `xliff_mcp/xliff_processor.py` (new `XliffProcessorService.diff_report` plus `_units_by_id`, `_target_parts`, `_state_of`, `_tag_skeleton`), `xliff_mcp/tool_registry.py` (new `diff_xliff_report` tool, report embedded in the `replace_xliff_targets` response, `get_server_info` list), `xliff_mcp/server.py` and `xliff_mcp/http_server.py` (export the callable), `README.md` (tool contract), `skills/replace_xliff_targets_from_translations.md`, `skills/catalog.json`, `tests/test_diff_report.py` (11 new tests).
- **Why**: the task asks for a diff report after every replacement run that flags any segment where tags, IDs or counts differ.
- **How**: `diff_report(original, filled)` reuses the same unit/target/inline-tag regexes as the fill path, so it reports on exactly what the writer touched. It reports `changed_units` (ids whose target text differs) and `issues`, each with `unit_id`, `kind` and `detail`. Kinds: `count`, `ids`, `source`, `attributes`, `state`, `tags`, `target`. It never raises on malformed input — a document that no longer parses is still compared textually.
- **Automatic**: `replace_xliff_targets` now includes `diff_report` in its JSON response, so the report runs on every replacement without a second call. The standalone tool exists for files filled elsewhere.
- **Contract change**: additive only. `replace_xliff_targets` keeps `content` and `replacements_count`; the response gains one key.
- **Not done**: the report does not verify XLIFF 1.2 schema order and does not check bidi control characters.

## Step 5 — deliverable for the owner's Smartcat test

### 2026-10-30 — local output directory

- **Files changed**: `.gitignore` (`out/`).
- **Reason**: the filled file and the translation map are derived from a real customer document. They must never be committed; `out/` is ignored so an accidental `git add -A` cannot pick them up.
- **Server behaviour changed**: none.

### 2026-10-30 — import confirmed, documentation only

- **Files changed**: `docs/review/tests.md` (owner's Smartcat import result), `docs/review/open-questions.md` (Q3 resolved, Q4 evidence).
- **Reason**: the owner imported the filled file: 178 segments imported, 5 skipped as "Target text not changed" (the untouched TM segments), no errors.
- **Server behaviour changed**: none.
