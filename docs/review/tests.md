# Tests — what was run, what was not

Append-only, one section per step. Commands are recorded exactly; output is quoted or summarised only where the summary adds nothing beyond the numbers shown.

## Step 1 (2026-10-30) — baseline and probes, no test files written

All commands run from the repository root, in the venv created with `python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"`.

### 1. Baseline suite

```
.venv/Scripts/python -m pytest -q
```

Result:

```
.....................                                                    [100%]
21 passed, 1 warning in 15.33s
```

The warning is a `pydantic_settings` `IncompleteFieldDefinitionWarning` raised from site-packages; unrelated to this repository.

### 2. Parsing the real Smartcat export

`/tmp/probe1.py` (scratch, outside the repo): `validate_xliff`, `process_xliff`, `process_xliff_with_tags` over `tests/fixtures/smartcat-acra-en-ar.xliff`.

Result: `(True, 'XLIFF format is valid', 183)`, 183 units in both paths. Selected units:

```
plain: source 'Page  of'      (inline <x/> lost)
tags : source 'Page <x id="1" ctype="x-smartcat" /> of'
tags : source 'REGISTRAR OF COMPANIES & BUSINESS NAMES'   (&amp; decoded to &)
```

### 3. Replacement against the real export

`/tmp/probe2.py`: four units replaced — one plain, one containing `&`, one with an `<x/>`, one with three `<g>`s.

- `replacements: 4`
- Filled units kept `state="needs-translation"`.
- The `&` unit was written as `… التجارية & أخرى`, and the document then failed to parse:

```
PARSE ERROR: xmlParseEntityRef: no name, line 1, column 42978 (<string>, line 1)
validate_xliff on output: (False, 'Invalid XLIFF format: xmlParseEntityRef: no name, line 1, column 42978 (<string>, line 1)', 0)
```

- Inline tags sent back verbatim (`<x/>`, `<g>`) survived intact.
- Document length changed from 45,377 to 45,611 bytes for those four replacements.

### 4. SDLXLIFF and plain XLIFF behaviour

`/tmp/probe3.py` over `tests/samples.py::SDL_XLIFF` and `SAMPLE_XLIFF`.

- SDL: `validate` → `(True, …, 2)`; `process_xliff_with_tags` target → `<mrk mid="0" mtype="seg">你好世界</mrk>`.
- SDL: after replacing unit `1` with plain text the target became `<target>مرحبا</target>` — the `<mrk mid="0" mtype="seg">` wrapper was dropped, while the header entry still read `<sdl:seg id="1" conf="Draft" …/>`.
- SDL: output still parsed (`(True, …, 2)`), i.e. the structural loss is **not** caught by `validate_xliff`.
- Plain XLIFF: replacement of unit `1` fine; unit `2` untouched.

### 5. Entity / XXE behaviour

`/tmp/probe4.py`:

```
XXE validate: (True, 'XLIFF format is valid', 1)
XXE unit.source: ''
billion-laughs validate: (True, 'XLIFF format is valid', 1)
```

Conclusion recorded in `findings.md` §6: no external entity is read and no entity is expanded with translate-toolkit 3.20.1; `validate_xliff` does not reject the DOCTYPE.

### 6. Fixture measurement

`/tmp/measure.py` and `/tmp/edge.py`: produced every number quoted in `findings.md` §3 (183 units, 178 empty/needs-translation, 5 translated, 11 tagged units, tag types `x`×5 and `g`×8, 2 units with `&amp;`, 0 duplicate ids, 0 elements with outer-edge whitespace).

### Not run in Step 1

- No property/schema validation against `xliff-core-1.2-strict.xsd` — the XSD was read for reference only; it is not wired into any test.
- No test against translate-toolkit versions other than 3.20.1 (in particular not against the declared floor `3.0.0`).
- No test of the HTTP transport, auth, or rate limiting.
- No round-trip through Smartcat itself (that is the owner's final acceptance step).
- No test with an Arabic or Persian *full-file* fill — only the four-unit probe above.

## Step 2 (2026-10-30) — invariant tests written first, suite is red

### Fixtures created

- `tests/fixtures/smartcat-en-ar.xliff` — anonymised derivation of the supplied export. The real file was removed from the working tree before this step.
- `tests/fixtures/plain-en-ar.xliff`, `tests/fixtures/plain-en-fa.xliff` — hand-written.
- `tests/fixtures/README.md` — provenance.

Anonymisation verification (`/tmp/verify_anon2.py`, run before the real file was deleted):

```
units SAME
ids SAME
attrnames SAME
tattrs SAME
sattrs SAME
tagskel SAME
header SAME
fileattrs SAME
last-modified-user values before/after: {'<username>'} -> {'Example User'}
```

Residual-name scan of the anonymised file (case-insensitive) for `<company>`, `<street>`, `<officer>`, `<username>`, `<id>`, `<id>`, `<id>`, `<uen>`, `<uen>`, `<receipt number>`, `<auditor>` returned `[]`.

### Test file

`tests/test_fill_invariants.py` — 16 tests. `assert_output_invariants()` is the whole contract in one function: unit count and id order, bytes outside `<target>`, `<source>` bytes per unit, target attributes except `state`, `state="translated"` on filled targets, untouched units byte-identical, XML well-formed, `validate_xliff` accepted, tag skeleton of a filled target equal to its source.

Five meta-tests take a filled document and break one thing, asserting the checker raises.

### Command and result (before any server change)

```
.venv/Scripts/python -m pytest tests/test_fill_invariants.py -q
```

```
10 failed, 6 passed in 1.64s
```

Full suite:

```
.venv/Scripts/python -m pytest -q
10 failed, 27 passed, 1 warning in 6.32s
```

The 10 failures are the defects listed in `findings.md` §5 — state never set, `&` written raw, whitespace stripped, extraction loses inline tags in the non-tag path, and (as a consequence) the five meta-tests cannot reach their own assertion because the baseline produced by the current code already violates the state invariant. They are expected to go green in Step 3; the meta-tests only become meaningful then.

### Not run in Step 2

- Nothing was run against Smartcat itself.
- No SDLXLIFF test was written (out of scope, Q1).
- The meta-tests do not yet demonstrate their own assertion (see above).

## Step 3 (2026-10-30) — after the fixes

### Commands and results

```
.venv/Scripts/python -m pytest tests/test_fill_invariants.py -q
```

```
14 passed in 1.47s        (first run, 2 test-helper bugs)
```

After fixing `tag_skeleton` (closing tags were counted) and the dropped-tag meta-test (it was editing the source):

```
.venv/Scripts/python -m pytest -q
37 passed, 1 warning in 3.95s
```

```
.venv/Scripts/ruff check .
All checks passed!
```

### Deliberate breakage, caught by the suite

`/tmp/demo.py` fills `plain-en-ar.xliff` correctly, then removes `<g id="2">10</g>` from one target and re-runs the contract checker:

```
clean fill -> checker: passes
deliberately dropped <g id="2">10</g> from target of unit 2:
  caught: unit 2: inline tags differ from source
```

Filled output for the two units concerned:

```
<target state="translated">المبلغ الإجمالي: 1,250.00 GBP</target>
<target state="translated" xml:space="preserve">صفحة <x id="1" /> من <g id="2">10</g></target>
```

### Smartcat spot check

`/tmp/sc_check.py` fills the seven units in `smartcat_translations()`:

```
replacements: 7
outside-target bytes identical: True
len%: 45344 45711
state="translated" count: 12 | needs-translation: 171
```

`12 = 5` pre-existing translated targets `+ 7` newly filled. `9216312`:

```
<source xml:space="preserve">REGISTRAR OF COMPANIES &amp; BUSINESS NAMES</source>
<target state="translated" xml:space="preserve">مسجل الشركات &amp; الأسماء التجارية</target>
```

### Not run in Step 3

- No full-file fill of the 178 empty Smartcat segments (that is Step 4's diff-report run).
- No run against Smartcat itself.
- `xliff_mcp/xliff_processor.py` was deliberately not passed through `ruff format` (pre-existing unformatted file; see changelog).
- Nothing tested on Python 3.10–3.13; only 3.14.7.

## Step 4 (2026-10-30) — diff report

### Commands and results

```
.venv/Scripts/python -m pytest -q
48 passed, 1 warning in 3.62s

.venv/Scripts/ruff check .
All checks passed!
```

The smoke script CI runs (`python test_server.py`) was run locally. On a Windows console with cp1252 output it fails while printing its own `✓`/`❌` glyphs (`UnicodeEncodeError: 'charmap' codec`), which is a console-encoding issue in the script, not a code failure. With UTF-8 output it completes:

```
PYTHONIOENCODING=utf-8 .venv/Scripts/python test_server.py
...
All tests completed successfully! ✓
```

### Full-file fill of the Smartcat fixture

`/tmp/fullfill.py` fills every empty segment by reusing the source's inline tags and replacing text runs with Arabic text, then asks for the report:

```
segments to fill: 178
replacements: 178
{"original_unit_count": 183, "filled_unit_count": 183, "counts_match": true}
changed: 178 | issues: 0
validate: (True, 'XLIFF format is valid', 183)
translated targets: 183 | needs-translation: 0
outside-target identical: True
```

This is a structural fill with placeholder Arabic, not a translation-quality test.

### Not run in Step 4

- No human-quality translation of the Smartcat file; the 178 filled segments above are placeholder text.
- No re-import into Smartcat (owner's acceptance step).
- The report was not tested against a document with duplicate `id` values across several `<file>` elements (Q7).

## Step 5 (2026-10-30) — real fill of the supplied ACRA export

The owner asked for the supplied export to be translated, to re-import into Smartcat themselves. The source file was copied to `out/source-en-ar.xliff` (untracked; `out/` added to `.gitignore`). The repository fixtures are unaffected.

### What was run

```
.venv/Scripts/python -I /tmp/dump_segments.py     # extract the 178 empty segments
.venv/Scripts/python -I /tmp/fill_real.py         # fill + diff report + write out/filled-en-ar.xliff
.venv/Scripts/python -I /tmp/verify_real.py       # independent checks on the result
```

### Result

```
segments: 178 | unique: 119 | untranslated sources: 0
replacements: 178 | changed: 178 | issues: 0
counts: 183 -> 183 match: True
validate: (True, 'XLIFF format is valid', 183)

outside-target identical: True
empty targets: []
state counts: 183 translated / 0 needs
bytes: 45413 -> 49834
```

29 targets still contain Latin tokens; every one was checked by hand and is intentional: `ACRA`, `(ACRA)`, `<notary number>`, the UEN/FIN/NRIC identifiers, the abbreviation codes `UL/UF/AR/AGM/FS/FYE`, `OpenAttestation`, `Business_Profile.oa`, the verification URL, and the receipt number.

37 targets are byte-identical to their source. They are the `:` separators, the identifier strings, the abbreviation codes and `ACRA` — nothing that can be translated.

The five segments that already had translation (`[Logo]`, `[Signature]` ×3) were not in the payload and came back byte-identical, including `state-qualifier="exact-match"` and `sc:match-quality="100"`.

### Translation choices (not verified by anyone but the author)

- Proper names are transliterated into Arabic: <company>, <parent company>, <auditor>, and the four officer names.
- Identifiers are left in Latin exactly as issued: UENs, FIN/NRIC numbers, notary number, receipt number, clearance codes.
- Dates keep the source's digits and use Arabic month names (`19 أكتوبر 2026`).
- `ACRA` stays Latin next to its Arabic expansion.

### Not run / not verified

- This is machine translation by a language model. It is not a certified translation and was not reviewed by an Arabic-speaking translator or a notary.
- It has not been imported into Smartcat. That is the owner's acceptance step.
- No check of Arabic typography beyond the structural checks above (no bidi-control characters were introduced by the tool; the translation text itself was written by the model).
