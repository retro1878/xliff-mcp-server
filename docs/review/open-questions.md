# Open questions

Items needing a decision from the repository owner. Each states the default that will be used if no answer arrives, so work is not blocked.

## Q1 — SDLXLIFF state vs "header stays byte-identical" — **RESOLVED 2026-10-30**

**Owner's answer:** SDLXLIFF is out of scope. Work only on `.xliff` files as exported by Smartcat.

**Consequence:** no `.sdlxliff` handling, no SDLXLIFF fixtures, no SDLXLIFF tests. The upstream test `test_sdl_xliff_uses_file_level_language_metadata` is left as it is (read-only language extraction, unaffected). `findings.md` §3 and §5 still describe the SDLXLIFF behaviour because it was observed; it is recorded as a known limitation, not a promise.

## Q2 — May the real Smartcat export be committed? — **RESOLVED 2026-10-30**

**Owner's answer:** anonymise it.

**Consequence:** `tests/fixtures/smartcat-en-ar.xliff` is a structurally identical derivation of the supplied export: same 183 units, same ids, same attribute names and values for `state`, `xml:space`, `approved`, `sc:locked`, `sc:last-modified-date`; the only values changed are company names, officer names, FIN/NRIC-style identifiers, UENs, the notary number, the receipt number, the auditor name, the address and `sc:last-modified-user`. Verified equal on unit count, id list, attribute-name sets, tag skeletons, `<header>` bytes and `<file>` attributes (`/tmp/verify_anon2.py`, recorded in `tests.md`). The real file was deleted from the working tree and is not in git history.

## Q3 — Which `state` should a filled target get? — **RESOLVED 2026-10-30**

**Answer:** `state="translated"`, as implemented.

**Evidence:** the owner imported a file with 178 segments set to `state="translated"` into the originating Smartcat project. Smartcat reported `Successfully imported: 178`, `Skipped: 5` (the five TM segments left untouched, reason "Target text not changed"), with no errors. Recorded in `tests.md`, Step 5.

## Q4 — Is setting `state` on a target that already has a translation acceptable?

If a run is repeated over a file that already has `state="translated"` plus `state-qualifier="exact-match"` and `sc:match-quality="100"`, the new text overwrites TM provenance while those attributes stay. Options: (a) leave attributes alone but overwrite text, (b) strip `state-qualifier`/`sc:match-quality` when overwriting, (c) skip units already `translated` unless explicitly forced.

**Default if unanswered:** (a). It is the smallest diff and the owner re-imports and confirms anyway; (b) and (c) are one-line additions if wanted later.

**Evidence added 2026-10-30:** on re-import Smartcat skips targets whose text did not change ("Target text not changed"), so untouched TM segments are not re-stamped. Overwriting a TM segment with new text would still leave its `state-qualifier`/`sc:match-quality` in place, which is the case option (b) would fix.

## Q5 — How should translations be delivered: plain text or tagged markup?

`process_xliff_with_tags` returns source with inline tags inlined (`Page <x id="1" ctype="x-smartcat" /> of`), implying the caller sends back the same shape. The Step 3/4 design accepts both: a string that parses as an XML fragment is treated as markup, anything else is escaped as text. A plain-text answer for a tagged source is then *structurally wrong but well-formed*, and only the Step 4 diff report catches it.

**Default if unanswered:** do not reject it in Step 3 (rejecting would fail silently for every untagged file); report it as a tag mismatch in the Step 4 diff report.

## Q6 — Should `validate_xliff` be strengthened? — **RESOLVED 2026-10-30**

**Answer:** yes, but as a second, separate answer.

`validate_xliff` keeps its original meaning: well-formed, parseable as XLIFF, correct unit count. It now also returns `schema_valid`, `schema_errors` and `ignored_extensions`, produced by `XliffProcessorService.schema_check()` against the OASIS XLIFF 1.2 strict schema (vendored at `xliff_mcp/schemas/xliff-core-1.2-strict.xsd`, shipped in the wheel).

The schema check tolerates vendor extensions and says which ones it ignored:

- elements and attributes in a foreign namespace (Smartcat's `sc:locked`, `sc:last-modified-date`, `sc:last-modified-user`, `sc:match-quality`);
- attributes with no namespace that the schema does not declare (`x-state-qualifier`), determined from the schema itself rather than a hand-written list.

Everything the schema declares is still enforced: required attributes, element order, `state` enumerations, inline element nesting.

Measured: the supplied Smartcat export is `schema_valid: true` after ignoring 381 extension instances of five distinct names; a document with a missing `<source>` or `state="bogus"` is `schema_valid: false`.

## Q7 — Multi-file XLIFF and duplicate ids — **RESOLVED 2026-10-30**

**Answer:** addressed.

- `replace_xliff_targets` now resolves a translation by `segNumber` first (a document-wide position, 1-based, matching what `process_xliff` returns), then by `unitId`. A payload entry that carries both is matched by position when the id is ambiguous.
- When several units share an id and the payload only has `unitId`, translations for that id are consumed in document order, one per occurrence. A single translation therefore fills one unit, not all of them.
- `diff_report` now walks units in document order instead of collapsing them into a dict, so duplicates are compared position by position. It reports `kind: "ids"` with `duplicate unit id ...`, an id mismatch at a position, or units missing/extra on either side.

Known limit: the report still cannot say which `<file>` a duplicate belongs to; it identifies units by id and position only.

## Q8 — `translate-toolkit` floor — **RESOLVED 2026-10-30**

**Answer:** `translate-toolkit>=3.20.1`.

`get_safe_xml_parser` (the parser with `resolve_entities=False`, `no_network=True`) first appears in tag `3.19.4` — checked by fetching `translate/misc/xml_helpers.py` at tags 3.19.0 (absent), 3.19.1–3.19.3 (absent) and 3.19.4 (present). The floor is set to 3.20.1 because that is the only version the test suite has been executed against; 3.19.4–3.20.0 are believed safe but were not run here.

