# Independent Code Review Findings

Date: 2026-10-30
Repository: `xliff-mcp-server` (`HEAD` at `db407ba`)

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
