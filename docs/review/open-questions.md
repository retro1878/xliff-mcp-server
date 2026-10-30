# Open questions

Items needing a decision from the repository owner. Each states the default that will be used if no answer arrives, so work is not blocked.

## Q1 — SDLXLIFF state vs "header stays byte-identical" (blocks Step 2/3)

The fill must set segment state. For Smartcat XLIFF 1.2 the state is `target/@state` — inside `<target>`, so it does not violate the byte-identical rule. For SDLXLIFF the state is `<sdl:seg id="N" conf="…"/>` inside `<header><sdl:seg-defs>`, i.e. the header must change.

**Default if unanswered:** for files whose root carries the `sdl` namespace, update the matching `<sdl:seg>` element's `conf` to `Translated` and change nothing else in the header; the Step 2 test will assert "header byte-identical except that one attribute value". For every non-SDLXLIFF file the header stays byte-identical.

## Q2 — May the real Smartcat export be committed? (blocks nothing, matters before pushing)

`tests/fixtures/smartcat-acra-en-ar.xliff` is a genuine ACRA business profile for <company>, with real officer names, NRIC/FIN-style identifiers and a notary number. It was provided for this task. Committing it to a public GitHub fork publishes those names.

**Default if unanswered:** keep it in the working tree, commit it locally, do **not** push the fork until the owner answers. If the answer is no, replace it with a structurally identical anonymised fixture created from it (same units, same tags, placeholder names) and note the substitution in `changelog.md`.

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
