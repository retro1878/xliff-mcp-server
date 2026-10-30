# Independent Code Review Findings

Date: 2026-10-30
Repository: `xliff-mcp-server` (`HEAD` at `db407ba`)

> Note added 2026-10-30: history below this review was rewritten to remove customer identifiers. `db407ba` is now `9c8b9aa`; `9223d35` is now `fe2fc9f`.

## 1. Independent Verification of Tests, Linter, Formatter, and Recorded Claims

All checks were executed directly against the repository using `.venv\Scripts\python.exe` (Python `3.14.7`, `translate-toolkit 3.20.1`, `lxml 6.1.3`, `mcp 1.28.1`):

| Check | Command Run | Actual Result | Claim in `docs/review/` |
| :--- | :--- | :--- | :--- |
| **Pytest suite** | `.\.venv\Scripts\pytest -v` | **61 passed, 1 warning** (`IncompleteFieldDefinitionWarning` from `pydantic_settings`) in `6.51s` | Matches `docs/review/tests.md` (Step 6) |
| **Ruff linter** | `.\.venv\Scripts\ruff check .` | **All checks passed!** (`0` errors; rules enabled: `E4, E7, E9, F`) | Matches `docs/review/tests.md` (Step 6) |
| **Ruff formatter** | `.\.venv\Scripts\ruff format --check ...` | **Fails** (`exit code 1`): `20 files would be reformatted` across the repo, including newly added `tests/test_diff_report.py`, `tests/test_multi_file.py`, and newly added lines in `xliff_mcp/xliff_processor.py` | **Contradicts** `AGENTS.md` (*"Run `ruff format` on Python files you change"*) |
| **Smoke script** | `.\.venv\Scripts\python test_server.py` | Passes when `PYTHONIOENCODING=utf-8` is set; fails under default Windows `cp1252` console encoding on `✓` | Matches `docs/review/tests.md` (Step 4) |
| **Bytecode compile** | `.\.venv\Scripts\python -m compileall -q xliff_mcp tests` | Passes (`exit code 0`) | Canonical check in `AGENTS.md` |
| **Fixtures & outputs** | Measured via `lxml` + `hashlib.md5` | `tests/fixtures/smartcat-en-ar.xliff`: `45,380` bytes (`183` units: `178` `needs-translation`, `5` `translated`); untracked `out/source-en-ar.xliff`: `45,413` bytes; `out/filled-en-ar.xliff`: `49,834` bytes, MD5 `580dc6f6ff35f495ae44fa33e751edfe` | Matches `docs/review/findings.md` and `docs/review/tests.md` |

---

## 2. Code Review Findings (Ordered by Severity)

### High Severity — Correctness & Data Integrity Bugs

#### 1. Double-replacement bug when payload entries contain both `segNumber` and `unitId`
- **Location:** `xliff_mcp/xliff_processor.py:346-388` (`XliffProcessorService.replace_xliff_targets`)
- **Claim vs. Reality:** `docs/review/open-questions.md` (Q7) claims: *"A payload entry that carries both is matched by position when the id is ambiguous."* And `TranslationReplacementData` (`xliff_mcp/models.py:36-41`) defines `segNumber: int` alongside `unitId: Optional[str] = None`.
- **Bug:** Each translation entry with both keys is inserted into **both** `wanted_by_id[unit_id]` (`:354-355`) and `wanted_by_position[seg_number]` (`:356-358`). During `rewrite`, when a unit matches via `wanted_by_position.get(position)` (`:372`), the duplicate entry in `wanted_by_id` is **never removed**. Conversely, if an earlier unit with the same `unitId` does not have a `wanted_by_position` entry, it falls back to `wanted_by_id` and consumes the translation meant for a later `segNumber`.
- **Reproduced:** On `TWO_FILES` (where `id="1"` appears at `segNumber=1` and `segNumber=3`), passing a single translation `[{"segNumber": 3, "unitId": "1", "aiResult": "غاما"}]` overwrites **both** unit 1 and unit 3 (`replacements_count == 2`, targets `['غاما', '', 'غاما']`).

#### 2. `process_xliff_with_tags` returns the wrong unit content when duplicate `unitId`s exist across `<file>` elements
- **Location:** `xliff_mcp/xliff_processor.py:244-245` (`process_xliff_with_tags`) and `xliff_mcp/xliff_processor.py:286-311` (`_extract_element_content`)
- **Claim vs. Reality:** Step 6 (`docs/review/changelog.md:90`) claims duplicate IDs across `<file>` elements were fixed for Q7, but only updated `replace_xliff_targets` and `diff_report`, leaving the tag-preserving read path broken.
- **Bug:** `_extract_element_content` runs `re.search` from the start of the raw document string using only `unit_id`. Every subsequent unit with a repeated `id` extracts the `<source>` and `<target>` of the **first** occurrence in the document. It also rescans the full XML string twice per unit (`O(N^2)` in unit count).
- **Reproduced:** Running `XliffProcessorService.process_xliff_with_tags("two.xliff", TWO_FILES)` returns `[(1, '1', 'Alpha'), (2, '2', 'Beta'), (3, '1', 'Alpha')]` — unit 3's source `"Gamma"` is replaced with `"Alpha"`.

#### 3. Round-trip corruption in `process_xliff_with_tags` → `replace_xliff_targets` when a tagged segment also contains `<` (from `&lt;`)
- **Location:** `xliff_mcp/xliff_processor.py:308` (`_extract_element_content`) and `xliff_mcp/xliff_processor.py:570-603` (`_render_fragment`)
- **Bug:** `_extract_element_content` calls `html.unescape(content)` on the entire inner XML fragment, turning `&lt;` in text into a literal `<` alongside raw inline tags like `<g id="1">`. On the write path, `_render_fragment` (`:578-579`) checks `if text.count("<") != len(tags): return escape(text)`. Because the unescaped `<` in text is not a full tag match, `text.count("<") != len(tags)` is `True`, causing `_render_fragment` to escape **all** inline tags (`<g id="1">` becomes `&lt;g id="1"&gt;`).
- **Reproduced:** For `<source>1 &lt; 2 <g id="1">text</g></source>`, `process_xliff_with_tags` extracts `'1 < 2 <g id="1">text</g>'`, and passing that back to `replace_xliff_targets` writes `<target state="translated">1 &lt; 2 &lt;g id="1"&gt;text&lt;/g&gt;</target>`, destroying the `<g id="1">` tag.

#### 4. `_render_fragment` can still emit malformed XML that breaks document parsing
- **Location:** `xliff_mcp/xliff_processor.py:34` (`INLINE_TAG`) and `xliff_mcp/xliff_processor.py:570-603` (`_render_fragment`)
- **Claim vs. Reality:** Both `_render_fragment`'s docstring (`:573-575`) and `docs/review/changelog.md:35-37` claim that `_render_fragment` guarantees model output *"can never produce a document that does not parse."*
- **Bug:** `INLINE_TAG` (`r"<(/?)([A-Za-z][\w:.-]*)((?:[^<>\"']|\"[^\"]*\"|'[^']*')*?)(/?)>"`) does not validate XML attribute syntax, entity references inside attribute values, namespace prefixes, or simultaneous `/` at both ends:
  - `</g/>` has both `closing == "/"` and `self_closing == "/"`; line 586 (`if self_closing: continue`) skips the closing check and writes `</g/>` raw (`XMLSyntaxError: expected '>'`).
  - `<x id="1 & 2"/>` (which also arises after `html.unescape` decodes `&amp;` inside an inline tag attribute) is written raw (`xmlParseEntityRef: no name`).
  - `<x bogus/>` or `<g id=1>hi</g>` is written raw (`Specification mandates value for attribute`).
  - `<ns:g>hi</ns:g>` (undeclared prefix `ns`, since `name.split(":")[-1]` is `"g"`) is written raw (`Namespace prefix ns on g is not defined`).
- **Reproduced:** All four strings above pass `_render_fragment` unescaped and cause `validate_xliff` to return `(False, "Invalid XLIFF format: ...", 0)`.

#### 5. Uncaught `lxml.etree.XMLSchemaValidateError` in `schema_check` breaks `validate_xliff` on DTD entities
- **Location:** `xliff_mcp/xliff_processor.py:168-184` (`schema_check`) and `xliff_mcp/tool_registry.py:127-144` (`validate_xliff`)
- **Claim vs. Reality:** `docs/review/findings.md:118-120` states the package never imports `lxml` (outdated after Step 6 added `from lxml import etree` at `xliff_processor.py:14`), and `docs/review/tests.md:66-70` claims `validate_xliff` returns `valid: True` on documents containing a `DOCTYPE` entity reference (`&xxe;`).
- **Bug:** Because `schema_check` parses with `resolve_entities=False`, an entity reference like `&xxe;` remains in the `lxml` tree as an `_Entity` node (`isinstance(element.tag, str)` is `False`, so `_strip_extensions` skips it). Calling `schema.validate(tree)` on a tree with an unresolved `_Entity` raises `lxml.etree.XMLSchemaValidateError: Internal error in XML Schema validation.`, which `schema_check` does not catch (it only catches `etree.XMLSyntaxError`). In `tool_registry.py:128-144`, this uncaught exception aborts `validate_xliff` and forces `"valid": False` with `"Validation error: Internal error in XML Schema validation."` and omits `schema_valid`/`schema_errors`.

#### 6. `_fill_target` corrupts `<alt-trans>` when `<trans-unit>` has no `<target>` yet
- **Location:** `xliff_mcp/xliff_processor.py:543-567` (`_fill_target`)
- **Bug:** `TARGET_ELEMENT.search(unit_content)` searches the entire inner body of `<trans-unit>`. In valid XLIFF 1.2 where a `<trans-unit>` has `<source>` and `<alt-trans><source>...</source><target>...</target></alt-trans>` (a TM/MT suggestion) but no unit-level `<target>` yet, `_fill_target` matches and overwrites the `<target>` inside `<alt-trans>` instead of inserting a `<target>` after `</source>` or `</seg-source>`.

#### 7. Word-boundary regex in `_with_translated_state` and `_state_of` matches hyphenated/namespaced attributes like `sc:state` or `x-state`
- **Location:** `xliff_mcp/xliff_processor.py:526-540` (`_with_translated_state`) and `xliff_mcp/xliff_processor.py:638-640` (`_state_of`)
- **Bug:** Because `:` and `-` are non-word characters in Python `re`, `\bstate\s*=` matches `sc:state="..."` and `x-state="..."`.
- **Reproduced:** On `<target sc:state="locked" state="needs-translation">`, `_with_translated_state` rewrites `sc:state` to `sc:state="translated"` and leaves `state="needs-translation"` unchanged. Then `_state_of` in `diff_report` also matches `sc:state="translated"` first and reports `issues: []` (missing the fact that `state` is still `"needs-translation"` and `sc:state` was mutated).

---

### Medium Severity — Validation & Diff Report Blind Spots

#### 8. `diff_report` misses malformed XML, mutated target attributes, nested/self-closing tag mismatches, and dropped duplicate IDs
- **Location:** `xliff_mcp/xliff_processor.py:393-518` (`diff_report`) and `xliff_mcp/xliff_processor.py:643-652` (`_tag_skeleton`)
- **Bugs verified:**
  - **Malformed XML passes with 0 issues:** If `filled` has a raw `&` inside `<target>` (`<target state="translated">أ & ب</target>`), `diff_report` compares it purely with regexes and returns `issues: []`.
  - **Target attribute mutations ignored:** `diff_report` checks `before["start_tag"] != after["start_tag"]` (the `<trans-unit>` tag) and `new_target["state"]`, but never checks whether `<target>` attributes (`xml:space="preserve"`, `state-qualifier`, `sc:match-quality`) were altered or deleted.
  - **Unchanged target text skips state/attribute checks:** At `xliff_processor.py:489-490`, `if old_target is not None and old_target["inner"] == new_target["inner"]: continue` skips units whose target text matches `old_target` even if `replace_xliff_targets` changed `state="needs-translation"` to `state="translated"` (causing `len(changed_units)` to disagree with `replacements_count`) or if `state` was broken on an existing target.
  - **`_tag_skeleton` ignores closing tags, self-closing vs. paired tags, and `ctype`:** `_tag_skeleton` (`:643-652`) only collects `localname:id` for non-closing tags. Turning `<g id="1">text</g>` into self-closing `<g id="1"/>`, nesting `<g id="1"><g id="2">...</g></g>` instead of sibling `<g id="1">...</g><g id="2">...</g>`, or dropping `ctype="x-smartcat"` all produce the same skeleton and trigger zero issues.
  - **Count mismatch fallback breaks on duplicate IDs:** When `len(original_units) != len(filled_units)` (`:436-450`), `filled_by_id = {unit["id"]: unit for unit in filled_units}` collapses duplicate IDs. Dropping one of two `id="1"` units in `TWO_FILES` fails to report the missing `id="1"` unit and instead falsely reports `{'unit_id': '1', 'kind': 'source', 'detail': 'source element changed'}`.

#### 9. `schema_check` strips any unknown unqualified attribute name, masking attribute typos
- **Location:** `xliff_mcp/xliff_processor.py:669-677` (`_known_attributes`) and `xliff_mcp/xliff_processor.py:680-705` (`_strip_extensions`)
- **Bug:** To work around Smartcat's unqualified `x-state-qualifier` attribute, `_strip_extensions` deletes *every* unqualified attribute whose name does not appear anywhere in the XSD (`_known_attributes()`), rather than restricting to `x-*` attributes. As a result, attribute typos such as `<trans-unit id="1" aprvd="no">` or `<target stte="bogus">` are stripped as `"ignored_extensions"` and reported as `schema_valid: True`. Conversely, when non-XLIFF XML (like `<html>` or `<tmx>`) is passed to `schema_check`, every non-XLIFF child element is stripped and listed under `ignored_extensions`.

#### 10. Multi-`<file>` language metadata always uses the first `<file>` element
- **Location:** `xliff_mcp/xliff_processor.py:66-72` (`process_xliff`) and `xliff_mcp/xliff_processor.py:314-329` (`_get_file_languages`)
- **Bug:** Both methods read `source-language` and `target-language` from the first `<file>` in the document rather than the enclosing `<file>` of each `<trans-unit>`. In a multi-`<file>` document where file 1 targets `ar` and file 2 targets `fa`, all units in file 2 are reported with `tgtLang="ar"`.

---

### Confidentiality, Repository Hygiene & Minor Issues

#### 11. Confidential customer data leaked in committed `docs/review/tests.md` and persisted in `out/`
- **Location:** `docs/review/tests.md:107` and `docs/review/tests.md:274-283`; `out/` directory on disk
- **Issue:** `docs/review/open-questions.md:11-15` (Q2) states the owner required anonymizing the real Smartcat export before committing, and `AGENTS.md:22` states: *"Treat user-supplied localization files as potentially confidential; do not persist inputs, translated content, exports, or raw tool payloads."* However:
  - Committed `docs/review/tests.md:107` and `:282` explicitly record the real company names, auditor name, Smartcat username, notary number, and numeric substrings that were scrubbed from the fixture.
  - The un-anonymized customer XLIFF and translation files (`out/source-en-ar.xliff`, `out/filled-en-ar.xliff`, `out/source-segments.json`, `out/translations.json`) remain persisted on disk in `out/`.

#### 12. HTTP Server, Auth & Documentation Minor Issues
- `RateLimiter.is_allowed` (`xliff_mcp/auth.py:101-121`) stores request timestamps per API key in an unbounded dict (`self.requests`) and is only invoked when `api_auth.enabled` is `True` (`xliff_mcp/http_server.py:55`); when unkeyed, rate limiting is bypassed completely, and there is no payload size limit on `content`.
- `SecurityHeaders` (`xliff_mcp/auth.py:124-137`) and `require_auth` (`xliff_mcp/auth.py:145-173`) in `auth.py` are dead code (never wired into `http_server.py` or `tool_registry.py`).
- `README.md:244` still lists `translate-toolkit >= 3.0.0` in the Requirements section while `pyproject.toml:24` was bumped to `translate-toolkit>=3.20.1`.

---

## 3. Re-Verification of Step 7 Fixes (`HEAD` at `cff05e7`)

Executed `.\.venv\Scripts\pytest -v` (**77 passed, 1 warning**), `.\.venv\Scripts\ruff check .` (**passed**), `.\.venv\Scripts\ruff format --check` on the test files, and targeted reproduction probes against `cff05e7`:

| # | Original Finding | Step 7 Status | Verification Details |
| :--- | :--- | :--- | :--- |
| **1** | Double-replacement when payload has both `segNumber` and `unitId` | **Covered** | `replace_xliff_targets` (`xliff_processor.py:385-392`) now stores entries with `segNumber` only under `wanted_by_position` and `continue`s. |
| **2** | `process_xliff_with_tags` returns first unit on duplicate `unitId`s | **Covered** | `process_xliff_with_tags` (`xliff_processor.py:232-276`) now indexes `raw_units` by document position instead of searching by `unit_id`. |
| **3** | `&lt;` in tagged segment destroys tags on round-trip | **Partially covered** | Fixed for `&lt;` in text runs (`1 &lt; 2 <g id="1">text</g>`), **but still broken when an inline tag attribute contains `&amp;` or `&lt;`** (e.g., `<ph id="1" equiv-text="A &amp; B"/>`): `_extract_element_content` (`:336`) runs `html.unescape` across the whole fragment including tag attributes, producing `equiv-text="A & B"`, which `_render_fragment` then rejects as invalid XML and escapes into `&lt;ph ...&gt;`. |
| **4** | `_render_fragment` passes malformed tag candidates through | **Partially covered** | Fixed for `</g/>`, `<x id="1 & 2"/>`, `<x bogus/>`, and `<ns:g>`, **but still broken for closing tags with attributes/trailing tokens** (e.g., `<g id="1">hello</g id="1">`): line 657 validates `f"<r><{name}></{name}></r>"` instead of `match.group(0)`, and line 683 writes `match.group(0)` (`</g id="1">`) raw into `<target>`, producing malformed XML (`validate_xliff` returns `False`). |
| **5** | Uncaught `XMLSchemaValidateError` in `schema_check` | **Covered** | `schema_check` (`xliff_processor.py:180-204`) now verifies the root tag is `{urn:oasis:names:tc:xliff:document:1.2}xliff` and catches `etree.XMLSchemaValidateError`. |
| **6** | `<alt-trans>` target handling | **Partially covered** | Fixed in `_fill_target` (`xliff_processor.py:613`), **but `_extract_element_content` (`:322-339`) and `_target_parts` (`:734-745`) still do not split before `<alt-trans>`**:<br>• If a unit has no `<target>` (only `<alt-trans><target state="translated" state-qualifier="fuzzy-match">old</target></alt-trans>`), `process_xliff_with_tags` extracts `'old'` as the unit target, and `diff_report` after filling falsely flags `kind: "attributes", detail: "target attributes changed"`.<br>• If a unit has a self-closing `<target state="needs-translation"/>` followed by `<alt-trans><source>s</source><target>old</target></alt-trans>`, `_extract_element_content` matches from `<target .../>` to `</target>` inside `<alt-trans>` and returns `'<alt-trans><source>s</source><target>old'` as `unit.target`. |
| **7** | `\bstate` matches `sc:state` / `x-state` | **Covered** | `_with_translated_state`, `_state_of`, `_tag_without_state`, and `_unit_id` now use `(?<![\w:-])`. |
| **8** | `diff_report` blind spots | **Covered (with 1 documented design choice)** | Added `_xml_problem` (`kind: "xml"`), `_tag_without_state` comparison (`kind: "attributes"`), `SequenceMatcher` alignment on count mismatch, and expanded `_tag_skeleton` to include `ctype`, self-closing `/`, and `/local` closing markers. (State-only edits with identical target inner text remain intentionally skipped, as documented in `review-response.md`.) |
| **9** | `schema_check` strips unknown unqualified attributes | **Covered** | `_strip_extensions` (`xliff_processor.py:806-839`) now only strips foreign-namespace items and `x-*` attributes; typos like `stte="x"` fail schema validation. |
| **10** | Multi-`<file>` language metadata always uses first `<file>` | **Half-covered** | Fixed in `process_xliff_with_tags` via `_languages_in_unit_order(content)` (`xliff_processor.py:233, 291-292`), **but `process_xliff` (`xliff_processor.py:61-74, 113-116`) was not updated** and still returns the first `<file>`'s `source-language`/`target-language` (`('en', 'ar')`) for every unit in `TWO_FILES`. |
| **11** | Confidential customer data in `docs/review/` and `out/` | **Mostly covered** | Scrubbed from `docs/review/tests.md` and git history (`git filter-branch` in `cff05e7`; `git log --all -S` for the company/user/auditor strings is now clean, and `backup/pre-scrub` was already deleted despite `changelog.md:110` saying it still exists). Note: `docs/review/tests.md:399` and `review-response.md:18,39` still contain stale notes saying history was not rewritten, and `out/` still holds the un-anonymized customer files on disk. |
| **12** | `README.md` floor, `ruff format` rule, & `auth.py` | **Partially covered** | `README.md:244` was updated to `translate-toolkit >= 3.20.1` (`auth.py` intentionally left out of scope). However, the newly added `tests/test_review_regressions.py` (along with `tests/test_diff_report.py` and `tests/test_multi_file.py`) still fails `ruff format --check`, violating `AGENTS.md:16`. |

---

## 4. Round 2 Re-Verification — Final Sign-Off (`HEAD` at `f1002c3`)

Re-ran `.\.venv\Scripts\pytest -v` (**82 passed, 1 warning**), `.\.venv\Scripts\ruff check .` (**All checks passed!**), `.\.venv\Scripts\ruff format --check` on all 5 added test files (**5 files already formatted**), and the reproduction script against `f1002c3`:

- **Finding #3 (Inline tag attribute entities on round-trip) — Covered:** `_unescape_text_runs` (`xliff_mcp/xliff_processor.py:708-711`) now unescapes only text runs between tags, keeping entities inside tag attributes intact (`<ph id="1" equiv-text="A &amp; B"/>` round-trips cleanly with `0` diff issues).
- **Finding #4 (Closing tags with attributes in `_render_fragment`) — Covered:** `_render_fragment` (`xliff_mcp/xliff_processor.py:664-667`) now requires closing tags to match `rf"</\s*{re.escape(name)}\s*>"` via `re.fullmatch`, escaping malformed closing tags such as `</g id="1">` so the output remains valid XML.
- **Finding #6 (`<alt-trans>` in `_extract_element_content` and `_target_parts`) — Covered:** Both `_extract_element_content` (`xliff_mcp/xliff_processor.py:334`) and `_target_parts` (`xliff_mcp/xliff_processor.py:757`) now call `_split_alt_trans`, preventing `<alt-trans><target>` from being read as the unit's own target or triggering false attribute diff issues.
- **Finding #10 (`process_xliff` multi-`<file>` languages) — Covered:** `process_xliff` (`xliff_mcp/xliff_processor.py:60-61, 81, 118-125`) now resolves per-unit languages via `_languages_in_unit_order(content)` by document position, returning `[('en', 'ar'), ('en', 'ar'), ('en', 'fa')]` on `TWO_FILES`.
- **Finding #11 (`out/` directory and stale history notes) — Covered:** `out/` has been removed from disk (`Test-Path out` is `False`), and the stale notes in `docs/review/{changelog,tests,review-response}.md` have been updated.
- **Finding #12 (`ruff format` on added test files) — Covered:** All five test files added in this fork (`test_fill_invariants.py`, `test_diff_report.py`, `test_multi_file.py`, `test_schema_validation.py`, `test_review_regressions.py`) pass `ruff format --check`.

All 12 findings are now fully covered.

---

## 5. Review of Post-Sign-Off Changes (`f1002c3..e31bd08` / `docs/review/change-report.md`)

### 5.1 Independent Verification of Tests, Linter, and Claims

| Check | Command Run | Actual Result | Claim in `change-report.md` |
| :--- | :--- | :--- | :--- |
| **Pytest suite** | `.\.venv\Scripts\pytest -v` | **87 passed, 1 warning** in `10.60s` (`+5` new tests in `tests/test_fill_invariants.py`) | Matches `change-report.md` §5 |
| **Ruff linter** | `.\.venv\Scripts\ruff check .` | **All checks passed!** (`0` errors) | Matches `change-report.md` §5 |
| **Ruff formatter** | `.\.venv\Scripts\ruff format --check ...` | **5 added test files pass** (`test_fill_invariants.py`, `test_diff_report.py`, `test_multi_file.py`, `test_schema_validation.py`, `test_review_regressions.py`). Note: modified upstream files (`tests/test_tools.py`, `xliff_mcp/tool_registry.py`, `xliff_mcp/xliff_processor.py`) still have pre-existing unformatted lines when checked as whole files. | Matches `tests.md` (Step 9) |
| **MCP tool descriptions (`912cd35`)** | `asyncio.run(mcp.list_tools())` | **10/10 tools** now expose non-empty `description` strings matching the docstrings in `xliff_mcp/tool_registry.py:82-391` | Matches `change-report.md` §2 (Change A) |
| **`.gitignore` (`4631bc9`)** | `git diff f1002c3..HEAD -- .gitignore` | `work/` added alongside `out/` | Verified |

---

### 5.2 Findings on Change B (`3898af4` — `require_tags` & `skipped_count`)

#### 13. `_tags_match_source` does not call `_split_alt_trans` and fails on self-closing `<source/>` (`Medium`)
- **Location:** `xliff_mcp/xliff_processor.py:872-879` (`_tags_match_source`)
- **Bug:** Unlike `_extract_element_content` (`:334`), `_fill_target` (`:628`), and `_target_parts` (`:757`), `_tags_match_source` searches raw `unit_content` directly with `SOURCE_ELEMENT = re.compile(r"<source\b[^>]*>[\s\S]*?</source>")` without first calling `_split_alt_trans(unit_content)` or checking for a self-closing `<source/>`.
- **Reproduced:** If a unit has a self-closing `<source/>` followed by `<alt-trans><source>Old <g id="1">tag</g></source>...</alt-trans>`, `SOURCE_ELEMENT.search(unit_content)` spans from `<source/>` across into `<alt-trans>`'s `</source>`, extracts `<g id="1">` from the `<alt-trans>` source, and wrongly rejects an untagged translation (`replacements_count == 0`).
- **Fix:** Split before `<alt-trans>` first (`unit_body, _ = _split_alt_trans(unit_content)`), and ignore self-closing `<source .../>` before searching with `SOURCE_ELEMENT` (matching `_extract_element_content`).

#### 14. `_tag_skeleton` enforces strict tag ordering, so `require_tags=True` rejects valid target-language tag reordering (`Medium`)
- **Location:** `xliff_mcp/xliff_processor.py:806-830` (`_tag_skeleton`) and `xliff_mcp/xliff_processor.py:872-879` (`_tags_match_source`)
- **Issue:** Noted as untested in `change-report.md` §6. Because `_tag_skeleton` returns an ordered `List[str]`, `_tags_match_source` requires inline tags to appear in the exact source order. In EN→AR/FA translation, grammatical word-order differences routinely require swapping two standalone placeholders or sibling `<g>` spans (e.g., `<source>From <x id="1"/> to <x id="2"/></source>` → `'إلى <x id="2"/> من <x id="1"/>'`).
- **Reproduced:** `XliffProcessorService.replace_xliff_targets` with `require_tags=True` rejects `'إلى <x id="2"/> من <x id="1"/>'` (`count == 0`) even though both tags are present, well-formed, and properly closed.
- **Recommendation:** While structural nesting and open/close pairing are already enforced by `_render_fragment` (which parses `<r>{text}</r>` via `lxml`), `_tags_match_source` should either compare the multiset (`Counter`) of tags (whilst still ensuring each paired `<g id="k">...</g>` wraps content rather than becoming self-closing) or document clearly that tag reordering requires `require_tags=False`.

#### 15. Round-trip mismatch when `<source>` contains escaped literal inline-tag syntax (`&lt;x id="1"/&gt;`) (`Low / Edge Case`)
- **Location:** `xliff_mcp/xliff_processor.py:723-726` (`_unescape_text_runs`) and `xliff_mcp/xliff_processor.py:872-879` (`_tags_match_source`)
- **Bug:** If a `<source>` contains literal escaped XML documentation text that looks like an XLIFF inline tag (e.g., `<source>Write &lt;x id="1"/&gt; in the file</source>`), `_tags_match_source` inspects the raw XML `inner` string (where `&lt;x id="1"/&gt;` is escaped text, so `_tag_skeleton(inner)` is `[]`). However, `process_xliff_with_tags` runs `_unescape_text_runs`, returning `'Write <x id="1"/> in the file'`. When the translator preserves that string and passes it back to `replace_xliff_targets`, `_render_fragment` treats `<x id="1"/>` as a real XML tag (`_tag_skeleton(rendered)` is `['x[1|/]']`), and `_tags_match_source` rejects the translation because `[] != ['x[1|/]']` (or, with `require_tags=False`, converts the escaped text into a real XML element).

#### 16. `skipped_count = len(translations_data) - replacements_count` conflates four distinct skip reasons (`Medium`)
- **Location:** `xliff_mcp/tool_registry.py:166-178` (`replace_xliff_targets`)
- **Issue:** Subtracting `replacements_count` from `len(translations_data)` counts all of the following as `skipped_count` with the single message `"(no matching unit, or the inline tags differed from the source)"`:
  1. A translation rejected by `_tags_match_source` (`require_tags=True`).
  2. An entry with an unknown `unitId` or out-of-range `segNumber`.
  3. An entry with an empty `aiResult`/`mtResult` (`""`).
  4. Duplicate `segNumber` entries in `translations_data` (where `wanted_by_position[int(seg_number)] = new_text` overwrites the earlier entry).
- **Reproduced:** Sending 4 entries (`1` unmatched `unitId`, `1` empty `aiResult`, and `2` entries with `segNumber=1` and valid tags) produces `replacements_count: 1, skipped_count: 3` even though zero units failed the tag check.

---

### 5.3 Answers to Reviewer Questions (`docs/review/change-report.md` §7)

1. **Where should `require_tags` live, and should it default to `True` in both `XliffProcessorService.replace_xliff_targets` and the MCP tool?**
   - **Yes — keep `require_tags: bool = True` as the default in both `XliffProcessorService.replace_xliff_targets` and the MCP tool.**
   - Protecting against stripped inline tags is a core invariant of XLIFF target replacement (broken tags corrupt CAT tool re-imports just like unescaped `&`), so direct Python callers and tests benefit from the same safe default as MCP tool callers, while `require_tags=False` provides an explicit opt-out.

2. **How should a skipped unit be reported in `diff_report` vs. `replace_xliff_targets`?**
   - **Keep `diff_report` pure (comparing only `original_content` vs. `filled_content`)** — `diff_xliff_report` is also a standalone MCP tool (`tool_registry.py:194-224`) that does not receive the `translations` payload, so it cannot know which untouched units were intentionally omitted from the payload versus skipped due to a tag mismatch.
   - **Report skipped units directly in `replace_xliff_targets`** by having `XliffProcessorService.replace_xliff_targets` track which translation entries were skipped and why.

3. **Should the skip reason be machine-checkable instead of only prose in `message`?**
   - **Yes.** Have `replace_xliff_targets` return a structured `skipped_units` list in the JSON response (and optionally from the service method or a helper), where each item records:
     ```json
     {"unit_id": "2", "seg_number": 2, "reason": "tags_mismatch"}
     ```
     with distinct `reason` codes (e.g., `"tags_mismatch"`, `"unit_not_found"`, `"empty_translation"`, `"duplicate_target"`). That way an MCP client can immediately see *which* unit failed tag validation and retry just that segment without guessing from `skipped_count`.

---

## 6. Round 3 Re-Verification (`HEAD` at `c972afc`)

Executed `.\.venv\Scripts\pytest -v` (**93 passed, 1 warning**), `.\.venv\Scripts\ruff check .` (**All checks passed!**), `.\.venv\Scripts\ruff format --check` on the 5 added test files (**5 files already formatted**), and targeted probes against `c972afc`:

| # | Round 2 Post-Sign-Off Finding | Step 11 (`c972afc`) Status | Verification Details |
| :--- | :--- | :--- | :--- |
| **13** | `_tags_match_source` ignores `<alt-trans>` and self-closing `<source/>` | **Partially covered** | Fixed in `_source_fragment` (`xliff_processor.py:926-936`) and `_fill_target` (`:692`) for the replacement path, **but `_units_in_order` (`xliff_processor.py:801-814`) — used by `diff_report` — still runs `SOURCE_ELEMENT.search(match.group(2))` on the raw unit body without `_split_alt_trans` or self-closing `<source/>` handling.**<br>• **Reproduced:** When `replace_xliff_targets` fills a unit with `<source/><alt-trans><source>Old <g id="1">tag</g></source>...</alt-trans>` by inserting `<target>` between `<source/>` and `<alt-trans>`, `SOURCE_ELEMENT` in `_units_in_order` spans from `<source/>` across the newly inserted `<target>` into `<alt-trans>`'s `</source>`. As a result, `diff_report` falsely reports two issues: `{'unit_id': '1', 'kind': 'source', 'detail': 'source element changed'}` and `{'unit_id': '1', 'kind': 'tags', 'detail': "source ['g[1|]', '/g'] != target []"}`! |
| **14** | Strict tag ordering rejects valid target-language tag reordering | **Partially covered** | Fixed in `_tags_match_source` (`xliff_processor.py:944-953`), which now compares `Counter(_tag_skeleton(...))`, **but `diff_report` (`xliff_processor.py:627-636`) still compares `source_tags != target_tags` as ordered lists instead of `Counter(source_tags) != Counter(target_tags)` (or `_tags_match_source`).**<br>• **Reproduced:** Calling the MCP tool `replace_xliff_targets` with `'إلى <x id="2"/> من <x id="1"/>'` succeeds (`replacements_count: 1, skipped_count: 0`), **but the `diff_report` returned in the very same response flags an error:** `{'unit_id': '1', 'kind': 'tags', 'detail': "source ['x[1|]/', 'x[2|]/'] != target ['x[2|]/', 'x[1|]/']"}`. |
| **15** | Escaped literal tag syntax in `<source>` (`&lt;x id="1"/&gt;`) round-trips into real markup | **Covered** | `_render_fragment(text, allowed=_source_tag_set(unit_content))` (`xliff_processor.py:452-454, 702-757`) only preserves inline tags present in the unit's own `<source>`, escaping any literal or hallucinated tags back to `&lt;...&gt;`. |
| **16** | `skipped_count` conflates four distinct skip reasons | **Covered** | `replace_xliff_targets_detailed` (`xliff_processor.py:380-484`) and the MCP tool `replace_xliff_targets` (`tool_registry.py:166-192`) now return `skipped_units: [{"unit_id", "seg_number", "reason"}]` with distinct `reason` codes (`"empty_translation"`, `"duplicate_target"`, `"unit_not_found"`, `"tags_mismatch"`). |

---

## 7. Round 4 Re-Verification — Final Sign-Off (`HEAD` at `797e67e`)

Re-ran `.\.venv\Scripts\pytest -v` (**96 passed, 1 warning**), `.\.venv\Scripts\ruff check .` (**All checks passed!**), `.\.venv\Scripts\ruff format --check` on all 5 added test files (**5 files already formatted**), and the Round 3/4 probe script against `797e67e`:

- **Finding #13 (`<alt-trans>` and self-closing `<source/>` in `diff_report`) — Covered:** `_units_in_order` (`xliff_mcp/xliff_processor.py:802-814`) and `diff_report` (`:627`) now use `_source_element` and `_source_fragment` (`:926-941`), which split at `<alt-trans>` and handle self-closing `<source/>`. Filling a unit with `<source/>` before `<alt-trans>` now produces `diff_report.issues == []`.
- **Finding #14 (Reordered placeholders in `diff_report`) — Covered:** `diff_report` (`xliff_mcp/xliff_processor.py:627-637`) now compares `Counter(source_tags) != Counter(target_tags)`, matching `_tags_match_source` (`:949-958`) while still flagging shape changes (such as paired `<g>` turned into self-closing `<g/>` or dropped `ctype`).

All 16 findings across all review rounds are now fully covered.





