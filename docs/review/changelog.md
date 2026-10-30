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

## Step 6 — Q6, Q7, Q8

### 2026-10-30 — schema validation, duplicate ids, dependency floor

- **Q6 — schema validation.** `xliff_mcp/xliff_processor.py`: added `schema_check()` plus `_xliff_schema`, `_known_attributes`, `_strip_extensions`, `_SCHEMA_LOCK`. Vendored `xliff_mcp/schemas/xliff-core-1.2-strict.xsd` (OASIS, copied unchanged). `tool_registry.validate_xliff` returns `schema_valid`, `schema_errors`, `ignored_extensions` alongside the existing fields. `valid` keeps its old meaning, so nothing that parsed before is rejected now.
  - *Reason*: `validate_xliff` only answered "translate-toolkit can parse it" (Q6). The strict schema alone rejects every real Smartcat export because of `x-state-qualifier` and the `sc:` attributes, so validation runs on a copy with vendor extensions removed and reports them.
- **Q7 — duplicate and multi-file ids.** `replace_xliff_targets` resolves by `segNumber` (document position) before `unitId`, and consumes duplicate-id translations in document order. `diff_report` compares units positionally instead of through a dict keyed by id, and reports duplicate ids, id mismatches and missing/extra units.
- **Q8 — dependency floor.** `pyproject.toml`: `translate-toolkit>=3.0.0` → `>=3.20.1` (first release with the safe parser is 3.19.4; only 3.20.1 has been run here).
- **Tests**: `tests/test_schema_validation.py` (7), `tests/test_multi_file.py` (6). Suite `61 passed`.
- **Regression check**: re-filling the supplied Smartcat export after these changes produced a byte-identical file (md5 `580dc6f6…` before and after), and it is `schema_valid: true` with five ignored extension names.

## Step 7 — response to the independent review

### 2026-10-30 — seven bugs fixed, one deliberate limit, one data scrub

- **Findings acted on**: 1–10 and 12 of `review-findings.md`, with a point-by-point disposition in `review-response.md`.
- **Files changed**: `xliff_mcp/xliff_processor.py` (`replace_xliff_targets` payload handling, `process_xliff_with_tags` + `_extract_element_content` positional extraction, `_render_fragment` per-tag validation, `_fill_target` `<alt-trans>` split, state/id attribute regexes, `schema_check` root check + exception handling, `_strip_extensions` restricted to `x-` and foreign namespaces, `diff_report` xml/attribute/tag checks + `SequenceMatcher`, `_tag_skeleton` structure, `_languages_in_unit_order`), `README.md` (dependency line), `docs/review/*` (scrub + this trail), `tests/test_review_regressions.py` (16 tests).
- **Data scrub**: real company names, username, identifiers and the notary number were removed from committed `docs/review/tests.md` (finding #11). They remain in the pushed history; rewriting it needs the owner's decision.
- **Not changed**: `xliff_mcp/auth.py` (unbounded rate-limit dict, unkeyed bypass, dead helpers) — upstream behaviour, out of scope for this task.
- **Result**: `76 passed`, `ruff check` clean, and the real filled export is still byte-identical (`580dc6f6…`).

### 2026-10-30 — history rewritten to remove customer identifiers

- **What**: `git filter-branch` over `main` replaced every customer identifier in `docs/review/*.md` across all commits (company and officer names, username, UEN/FIN/NRIC values, notary number, receipt number, address). Then `main` was force-pushed.
- **Why**: finding #11; the strings were removed from the working tree but remained in every commit from `896542b` onward.
- **Result**: commit SHAs changed. `896542b`→`70743e3`, `9223d35`→`fe2fc9f`, `6f9aab2`→`2aae2b2`, `9f35b8b`→`202970e`, `1c9ebfc`→`2dda4f2`, `5f9e86d`→`428e5d3`, `db407ba`→`9c8b9aa`, `0a6b3e9`→`229ed3f`. The working tree at `HEAD` is unchanged (`git diff 0a6b3e9 HEAD` was empty).
- **Backup**: a local-only branch `backup/pre-scrub` held the old history and was deleted on the owner's instruction; `git gc --prune=now` followed.

## Step 8 — second review round

### 2026-10-30 — four partial fixes completed

- **#3**: `_extract_element_content` unescapes text runs only (`_unescape_text_runs`), so entities inside inline tag attributes are preserved.
- **#4**: `_render_fragment` only accepts a closing tag that is exactly `</name>`.
- **#6**: `_split_alt_trans` is now used by `_extract_element_content` and `_target_parts` as well as `_fill_target`, so `<alt-trans>` content is never read as the unit's own source or target.
- **#10**: `process_xliff` resolves languages per `<file>` (`_languages_in_unit_order` + position), matching `process_xliff_with_tags`.
- **#12**: `tests/test_review_regressions.py`, `tests/test_diff_report.py`, `tests/test_multi_file.py` run through `ruff format`.
- **Docs**: stale statements about the un-rewritten history corrected.
- **Result**: `82 passed`; real export still byte-identical (`580dc6f6…`).

### 2026-10-30 — `out/` deleted

- **What**: removed `out/` from the working tree (source export, filled file, segment dump and translation map).
- **Why**: the owner imported the filled file into Smartcat and asked for the local copies to go; finding #11 is now fully closed.
- **Server behaviour changed**: none.

## Step 9 — tool descriptions

### 2026-10-30 — make the tools self-describing

- **Files changed**: `xliff_mcp/tool_registry.py` (one docstring per tool), `docs/review/changelog.md`.
- **Why**: the MCP `tools/list` response carried names and schemas only, so a client had to guess which of the ten tools to call and when.
- **How**: FastMCP turns each function's docstring into the tool description. Verified against a live `tools/list`: all ten now return text telling the model what the tool does and, for the two read paths, which one to use.
- **Server behaviour changed**: no tool signature or output changed; `82 passed`.

## Step 10 — tag enforcement on fill

### 2026-10-30 — `require_tags`

- **Files changed**: `xliff_mcp/xliff_processor.py` (`replace_xliff_targets(..., require_tags=True)` and `_tags_match_source`), `xliff_mcp/tool_registry.py` (parameter, `skipped_count`, message), `README.md`, `skills/replace_xliff_targets_from_translations.md`, tests.
- **Why**: the fill wrote a translation even when it had lost an inline placeholder, leaving a Smartcat segment without its `<x/>`/`<g>` marker. The owner's requirement is that a filled target mirrors the source's tags.
- **How**: before writing, the rendered target's tag skeleton is compared with the source's. On a mismatch the unit is left untouched (still `needs-translation`) and counted as skipped. `require_tags=False` restores the old behaviour.
- **Not added, deliberately**: no alignment of free-form translated documents to segments, and no automatic re-insertion of tags into tagless translations. Both need language understanding; they stay with the agent, which already receives the source segments with their tags.
- **Result**: `87 passed`.

## Step 11 — review round 3

### 2026-10-30 — structured skip report, tag matching by multiset

- **Answers accepted**: `require_tags` stays default-`True`; `diff_report` stays a pure comparison; the fill itself reports which translations were skipped and why.
- **Files changed**: `xliff_mcp/xliff_processor.py` (`replace_xliff_targets_detailed`, `_source_fragment`, `_source_tag_set`, multiset `_tags_match_source`, `_render_fragment(..., allowed)`, `_fill_target` anchor for self-closing source), `xliff_mcp/tool_registry.py` (`skipped_units`, message summary), `README.md`, skills, tests.
- **Why**: findings 13–16 of `review-findings.md` §5.
- **Behaviour**: tags may be reordered (languages change word order); a tag the source does not have is escaped rather than written; skip reasons are machine-readable.
- **Result**: `93 passed`.

## Step 12 — review round 3 re-verification

### 2026-10-30 — diff_report aligned with the fill

- **Files changed**: `xliff_mcp/xliff_processor.py` (`_units_in_order` uses `_source_element`; the tag check compares `Counter`s), `tests/test_review_regressions.py` (3 tests), `docs/review/*`.
- **Why**: findings 13 and 14 of `review-findings.md` §6 — the fill had been fixed but the report still used the old source extraction and ordered comparison, so it reported issues for a fill it had accepted.
- **Result**: a clean fill of either case now reports `issues: []`; a tag whose shape changes is still flagged. `96 passed`.
