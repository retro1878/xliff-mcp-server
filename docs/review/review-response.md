# Response to the independent review

Review under discussion: `docs/review/review-findings.md` (Argon, 2026-10-30, against the commit now known as `9c8b9aa` after the history rewrite).
Every finding was reproduced before being acted on; the reproduction output is in `tests.md` under Step 7. Fixes are in the commit that follows this file.

## Status at a glance (end of 2026-10-30)

All twelve findings are closed. No code finding is open; the remaining items are upstream behaviour that was deliberately left alone.

| Area | State |
| --- | --- |
| Findings 1–10, 12 | Fixed, each with a named test in `tests/` |
| Finding 11 | Docs scrubbed, history rewritten and force-pushed, `out/` deleted |
| Test suite | `82 passed` (`.venv/Scripts/python -m pytest -q`) |
| Linter | `ruff check .` — all checks passed |
| Real export round trip | still byte-identical, md5 `580dc6f6ff35f495ae44fa33e751edfe` |
| Deliberately unchanged | `auth.py` (rate-limit dictionary, unkeyed bypass, dead helpers), pre-existing unformatted files |
| Known limits | state-only edits with unchanged text are not reported by `diff_report`; duplicate unit ids are identified by id and position only |
| Reviewer sign-off | `review-findings.md` §4 (Argon, `f1002c3`): all 12 findings covered |

| # | Finding | Verdict | Where |
| --- | --- | --- | --- |
| 1 | Entry with both `segNumber` and `unitId` fills two units | Confirmed, fixed | `replace_xliff_targets` |
| 2 | `process_xliff_with_tags` returns the first unit for repeated ids | Confirmed, fixed | `process_xliff_with_tags` |
| 3 | `&lt;` in a tagged segment destroys tags on round trip | Confirmed, fixed | `_render_fragment` |
| 4 | `_render_fragment` passes malformed tag candidates through | Confirmed, fixed | `_render_fragment` |
| 5 | `schema_check` raises on unresolved entities | Confirmed, fixed | `schema_check` |
| 6 | `_fill_target` writes into `<alt-trans>` | Confirmed, fixed | `_fill_target` |
| 7 | `\bstate` matches `sc:state` / `x-state` | Confirmed, fixed | `_with_translated_state`, `_state_of`, `_unit_id` |
| 8 | `diff_report` blind spots | Confirmed, fixed except one deliberate limit | `diff_report`, `_tag_skeleton` |
| 9 | `schema_check` strips any unknown unqualified attribute | Confirmed, fixed | `_strip_extensions` |
| 10 | Languages always come from the first `<file>` | Confirmed, fixed | `_languages_in_unit_order` |
| 11 | Customer data in committed docs | Confirmed, scrubbed, history rewritten, `out/` deleted | `docs/review/tests.md` |
| 12 | README dependency line, auth dead code | README fixed; auth left untouched | `README.md` |

## What was done for each

1. **#1** A payload entry carrying `segNumber` is now stored only under that position and never queued by id. Repro before: `[{segNumber: 3, unitId: "1"}]` filled units 1 and 3 (`count 2`, `['غاما','','غاما']`). After: `count 1`, `['','','غاما']`. Test: `test_entry_with_both_keys_fills_only_its_position`.
2. **#2** `process_xliff_with_tags` no longer searches the document for an id. The i-th non-header unit of the store is matched to the i-th `<trans-unit>` by position, so repeated ids read their own body, and the per-unit work is no longer O(N²) in document size. Test: `test_with_tags_uses_each_units_own_body_with_duplicate_ids`.
3. **#3** A stray `<` from `html.unescape` no longer forces the whole fragment to be escaped. Text between kept tags is escaped run by run, so `1 < 2 <g id="1">text</g>` comes back as `1 &lt; 2 <g id="1">text</g>`. Test: `test_lt_round_trip_keeps_tags_and_escapes_the_less_than`.
4. **#4** Every tag candidate is parsed on its own before it is trusted: a self-closing tag as `<r>{tag}</r>`, an opening tag with a synthetic close, a closing tag against a synthetic open. `</g/>`, `<x id="1 & 2"/>`, `<x bogus/>` and `<ns:g>` are all rejected and escaped. Tests: `test_unusable_tag_candidates_are_escaped_not_written_raw`.
5. **#5** `schema_check` checks the root is `{…xliff} xliff`, and catches `XMLSchemaValidateError` around validation. A document with an entity reference now returns `valid: false` with a message instead of raising. Tests: `test_document_with_an_entity_reference_does_not_raise`, `test_validate_tool_survives_the_same_document`.
6. **#6** `_fill_target` splits the unit at the first `<alt-trans` and only ever writes before it. A unit without a target gets one after `</seg-source>`/`</source>`; the suggestion inside `<alt-trans>` is untouched. Test: `test_alt_trans_target_is_never_touched`.
7. **#7** Attribute-name patterns now use `(?<![\w:-])` instead of `\b`. `<target sc:state="locked" state="needs-translation">` keeps `sc:state` and gets `state="translated"`. Test: `test_namespaced_state_attribute_is_not_rewritten`.
8. **#8** Four of the five sub-findings are fixed:
   - malformed `filled` is reported as an issue of kind `xml` (`test_diff_report_flags_malformed_output`);
   - `<target>` attributes other than `state` are compared (`test_diff_report_flags_changed_target_attributes`);
   - `_tag_skeleton` now records name, id, `ctype`, self-closing and close markers, so a pair becoming self-closing or losing `ctype` is caught (`test_diff_report_flags_a_pair_turned_into_self_closing`, `test_diff_report_flags_a_dropped_ctype`);
   - when counts differ, alignment uses `difflib.SequenceMatcher` on the id sequence instead of a dict, so a dropped duplicate is reported as a missing unit (`test_diff_report_reports_a_dropped_duplicate_unit_by_id`).

   **Not fixed, by design:** a unit whose target text is byte-identical before and after is still skipped, so `changed_units` stays "units whose target text changed" and a state-only edit is not reported. That is the definition the tool has used since Step 4, and `replace_xliff_targets` always rewrites the text when it writes the state, so a real fill cannot hit it.
9. **#9** Only unqualified attributes starting with `x-` are treated as extensions, plus genuine foreign-namespace elements and attributes. Everything else the schema does not know is left in place, so `<source stte="x">` fails validation. A non-XLIFF root is rejected. Tests: `test_attribute_typo_fails_the_schema`, `test_non_xliff_root_is_rejected`. The schema-derived `_known_attributes()` helper was deleted; it is no longer needed.
10. **#10** `_languages_in_unit_order()` walks `<file>` blocks and returns the language pair of the file that encloses each unit. Test: `test_with_tags_reads_languages_from_the_enclosing_file`.
11. **#11** The committed strings were scrubbed in this commit: the real names, username, identifiers and notary number are gone from `docs/review/tests.md`. The `out/` copies remain on disk because the owner asked for the filled file and it is gitignored. **The strings are still in the pushed git history** (commits `9223d35` (now `fe2fc9f`) and later); removing them from history requires a rewrite and force-push, which is the owner's decision.
12. **#12** `README.md` now says `translate-toolkit >= 3.20.1`. `RateLimiter`'s unbounded dict, the unkeyed-HTTP bypass, the missing payload size limit and the dead `SecurityHeaders`/`require_auth` code are upstream issues that predate this work; they are recorded here and left untouched, because changing the HTTP transport's behaviour was not part of this task.

## Corrections to our own documentation

- `findings.md` §6 says the package never imports lxml. That was true in Step 1 and is no longer true: `schema_check` (Step 6) imports `lxml.etree` directly. A note has been added to that section.
- `changelog.md` Step 6 said duplicate ids across `<file>` were "fixed" for Q7; they were fixed for the write path and the report only. The read path is fixed in this commit.

## Verification

```
.venv/Scripts/python -m pytest -q          76 passed
.venv/Scripts/ruff check .                 All checks passed!
```

Re-filling the real export after the renderer rewrite produced the same byte-identical file (`md5 580dc6f6ff35f495ae44fa33e751edfe`), and `schema_check` still reports it valid. New tests: 16 in `tests/test_review_regressions.py`.

## Round 2 — Argon's re-verification (`review-findings.md` §3)

Four partial fixes were reported; all four were reproduced and fixed. Two are edge cases of the same code the first round touched, one is a read-path asymmetry, one a missed call site.

| # | Argon's note | Verdict | Fix |
| --- | --- | --- | --- |
| 3 | Inline tag **attributes** containing `&amp;` are still destroyed on round trip | Confirmed, fixed | `_unescape_text_runs()` unescapes only text between tags; `<ph equiv-text="A &amp; B"/>` survives |
| 4 | Closing tag with attributes (`</g id="1">`) written raw | Confirmed, fixed | `_render_fragment` requires a closing tag to match `</name>` exactly before keeping it |
| 6 | `_extract_element_content` and `_target_parts` still read inside `<alt-trans>` | Confirmed, fixed | both now split at `<alt-trans` via `_split_alt_trans()`, as `_fill_target` already did |
| 10 | `process_xliff` still uses the first `<file>`'s languages | Confirmed, fixed | it now uses `_languages_in_unit_order()` with a document position, like the tag path |
| 11 | stale notes about the history rewrite; `out/` still on disk | Confirmed, corrected | notes updated; `out/` deleted |
| 12 | new test files failed `ruff format --check` | Confirmed, fixed | the three new test files were formatted; the rest of the tree was already unformatted upstream |

Tests added for these: `test_tag_attribute_entities_survive_round_trip`, `test_closing_tag_with_attributes_is_escaped`, `test_alt_trans_only_target_is_neither_read_nor_reported`, `test_self_closing_target_before_alt_trans_is_not_read_as_target`, `test_process_xliff_reads_languages_per_file`.

```
.venv/Scripts/python -m pytest -q     82 passed
.venv/Scripts/ruff check .            All checks passed!
md5 out/filled-en-ar.xliff            580dc6f6ff35f495ae44fa33e751edfe  (unchanged)
```

## Round 3 — Argon's review of the post-sign-off work (`review-findings.md` §5)

### Answers accepted

| Question | Answer | What changed |
| --- | --- | --- |
| Default of `require_tags` | Keep `True` in both the service and the tool | none — already the case |
| Where skips are reported | Keep `diff_report` pure; report skips from `replace_xliff_targets` | `diff_report` untouched; the fill now reports them |
| Machine-checkable reasons | Yes, structured `skipped_units` | `replace_xliff_targets_detailed()` + `skipped_units` in the tool response |

`skipped_units` is a list of `{"unit_id", "seg_number", "reason"}`, with `reason` one of `empty_translation`, `duplicate_target`, `unit_not_found`, `tags_mismatch`. `skipped_count` is now its length, and the message summarises the reasons (`2 skipped (tags_mismatch: 1, unit_not_found: 1)`).

### Findings

| # | Finding | Verdict | Fix |
| --- | --- | --- | --- |
| 13 | `_tags_match_source` ignores `<alt-trans>` and self-closing `<source/>` | Confirmed, fixed | new `_source_fragment()` splits at `<alt-trans>` and treats a self-closing source as empty; `_fill_target` also anchors on a self-closing `<source/>` |
| 14 | Strict tag ordering rejects legitimate translations | Confirmed, fixed | the comparison is now a `Counter` over the tag skeleton: order may change, identity/ctype/pairing/self-closing may not |
| 15 | Escaped literal tag syntax in source text round-trips into real markup | Confirmed, fixed | `_render_fragment(text, allowed=source_tags)` treats any tag the source does not have as text, so a translation can never introduce markup |
| 16 | `skipped_count` conflates four reasons | Confirmed, fixed | per-entry reasons, as above |

Finding 15's fix also closes a related hole nobody reported: a hallucinated tag such as `<g id="9">` in a translation is now escaped as text instead of written into the target.

```
.venv/Scripts/python -m pytest -q     93 passed
.venv/Scripts/ruff check .            All checks passed!
```

Six new tests in `tests/test_review_regressions.py` cover 13–16 and the structured report.

### One behaviour to note

Because only source tags are allowed, a translation may no longer *add* markup. That is intended, but it means a caller who was relying on the fill to format text (for example wrapping a term in `<g>`) will now get the tags escaped. No such caller exists in this repository.

## Round 4 — Argon's re-verification of round 3 (`review-findings.md` §6)

Findings 13 and 14 were only half-fixed: the fill changed, `diff_report` did not. Both are now consistent.

| # | Was | Now |
| --- | --- | --- |
| 13 | `_units_in_order` read `<source>` from the raw unit body, so after a fill inserted `<target>` between `<source/>` and `<alt-trans>`, the source span leaked into `<alt-trans>` and the report claimed "source element changed" plus a tag issue | `_units_in_order` uses `_source_element()`, which splits at `<alt-trans>` and returns the unit's own `<source>`; filling that unit now reports `issues: []` |
| 14 | the report compared ordered tag lists, so a reorder the fill had accepted was reported as an error in the same response | the report compares `Counter` multisets, like the fill; shape changes (paired → self-closing, dropped `ctype`) are still flagged |

The fill gate and the report now use the same two helpers (`_source_fragment`, `_tag_skeleton` + `Counter`), so they cannot drift apart again without a test failing.

```
.venv/Scripts/python -m pytest -q     96 passed
.venv/Scripts/ruff check .            All checks passed!
```

Three new tests: no issues after filling a unit with a self-closing source and `<alt-trans>`; no issues after an accepted placeholder reorder; a tag that changes shape is still flagged.
