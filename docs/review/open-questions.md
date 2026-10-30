# Open questions

Items needing a decision from the repository owner. Each states the default that will be used if no answer arrives, so work is not blocked.

## Q1 — SDLXLIFF state vs "header stays byte-identical" — **RESOLVED 2026-10-30**

**Owner's answer:** SDLXLIFF is out of scope. Work only on `.xliff` files as exported by Smartcat.

**Consequence:** no `.sdlxliff` handling, no SDLXLIFF fixtures, no SDLXLIFF tests. The upstream test `test_sdl_xliff_uses_file_level_language_metadata` is left as it is (read-only language extraction, unaffected). `findings.md` §3 and §5 still describe the SDLXLIFF behaviour because it was observed; it is recorded as a known limitation, not a promise.

## Q2 — May the real Smartcat export be committed? — **RESOLVED 2026-10-30**

**Owner's answer:** anonymise it.

**Consequence:** `tests/fixtures/smartcat-en-ar.xliff` is a structurally identical derivation of the supplied export: same 183 units, same ids, same attribute names and values for `state`, `xml:space`, `approved`, `sc:locked`, `sc:last-modified-date`; the only values changed are company names, officer names, FIN/NRIC-style identifiers, UENs, the notary number, the receipt number, the auditor name, the address and `sc:last-modified-user`. Verified equal on unit count, id list, attribute-name sets, tag skeletons, `<header>` bytes and `<file>` attributes (`/tmp/verify_anon2.py`, recorded in `tests.md`). The real file was deleted from the working tree and is not in git history.

## Q3 — Which `state` should a filled target get?

`translated` is the XLIFF 1.2 value for "has been translated" and is what Smartcat's own TM-filled segments carry. `needs-review-translation` would be defensible if these are machine translations needing review. `state-qualifier="mt-suggestion"` is the spec value for machine output, but Smartcat's imported files only ever show `exact-match`, so adding a qualifier may confuse the importer.

**Default if unanswered:** set `state="translated"`, leave every other target attribute untouched, do not add `state-qualifier`.

## Q4 — Is setting `state` on a target that already has a translation acceptable?

If a run is repeated over a file that already has `state="translated"` plus `state-qualifier="exact-match"` and `sc:match-quality="100"`, the new text overwrites TM provenance while those attributes stay. Options: (a) leave attributes alone but overwrite text, (b) strip `state-qualifier`/`sc:match-quality` when overwriting, (c) skip units already `translated` unless explicitly forced.

**Default if unanswered:** (a). It is the smallest diff and the owner re-imports and confirms anyway; (b) and (c) are one-line additions if wanted later.

## Q5 — How should translations be delivered: plain text or tagged markup?

`process_xliff_with_tags` returns source with inline tags inlined (`Page <x id="1" ctype="x-smartcat" /> of`), implying the caller sends back the same shape. The Step 3/4 design accepts both: a string that parses as an XML fragment is treated as markup, anything else is escaped as text. A plain-text answer for a tagged source is then *structurally wrong but well-formed*, and only the Step 4 diff report catches it.

**Default if unanswered:** do not reject it in Step 3 (rejecting would fail silently for every untagged file); report it as a tag mismatch in the Step 4 diff report.

## Q6 — Should `validate_xliff` be strengthened?

Today it answers "translate-toolkit can parse this". The task's acceptance criterion is "XML stays well-formed and passes validate_xliff", which as written is weaker than schema validity. Wiring in the OASIS XSD would break inputs that parse today (including any file with an SDLXLIFF `<mrk mid>` or a DOCTYPE).

**Default if unanswered:** leave `validate_xliff` semantics unchanged; add a separate structural check inside the test suite and the diff report, and say so in `tests.md`.

## Q7 — Multi-file XLIFF

Ids are resolved document-wide, first match wins. Smartcat exports seen so far are single `<file>`. Supporting multi-file properly means scoping the regex to the enclosing `<file>` and reporting which file a unit belongs to.

**Default if unanswered:** not addressed in Steps 2–4; recorded as a known limitation in `findings.md` §5 and in the diff report's caveats.

## Q8 — `translate-toolkit` floor

The safe-parser behaviour in `findings.md` §6 was observed on 3.20.1 only; `pyproject.toml` allows `>=3.0.0`. Raising the floor is a dependency change and the rules say no dependency changes without asking.

**Default if unanswered:** no change to `pyproject.toml`; the caveat is recorded.
