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
last-modified-user value replaced with a placeholder: {'<real username>'} -> {'Example User'}
```

Residual-name scan of the anonymised file for every removed company name, person name, identifier, address, notary number and receipt number returned `[]`.

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

29 targets still contain Latin tokens; every one was checked by hand and is intentional: `ACRA`, `(ACRA)`, the notary number, the UEN/FIN/NRIC identifiers, the abbreviation codes `UL/UF/AR/AGM/FS/FYE`, `OpenAttestation`, `Business_Profile.oa`, the verification URL and the receipt number.

37 targets are byte-identical to their source. They are the `:` separators, the identifier strings, the abbreviation codes and `ACRA` — nothing that can be translated.

The five segments that already had translation (`[Logo]`, `[Signature]` ×3) were not in the payload and came back byte-identical, including `state-qualifier="exact-match"` and `sc:match-quality="100"`.

### Translation choices (not verified by anyone but the author)

- Proper names are transliterated into Arabic: the company, its parent company, the audit firm and the four officer names.
- Identifiers are left in Latin exactly as issued: UENs, FIN/NRIC numbers, notary number, receipt number, clearance codes.
- Dates keep the source's digits and use Arabic month names (`19 أكتوبر 2026`).
- `ACRA` stays Latin next to its Arabic expansion.

### Not run / not verified

- This is machine translation by a language model. It is not a certified translation and was not reviewed by an Arabic-speaking translator or a notary.
- It has not been imported into Smartcat. That is the owner's acceptance step.
- No check of Arabic typography beyond the structural checks above (no bidi-control characters were introduced by the tool; the translation text itself was written by the model).

### Smartcat import result — reported by the repository owner

The owner imported `out/filled-en-ar.xliff` into the same Smartcat project:

```
Successfully imported: 178
Skipped: 5
```

Every skipped segment (`9216142`, `9216146`, `9216155`, `9216240`, `9216314`) was skipped with **"Target text not changed"** — they are the five segments Smartcat had already filled from translation memory, which this run deliberately left untouched. No errors were reported.

This confirms, for this file and this Smartcat project:

- the file was accepted (namespace, header, ids, attribute set intact);
- the 178 filled targets were stored as translations, i.e. `state="translated"` was accepted;
- leaving already-translated segments untouched produces "skipped", not an error.

## Step 6 (2026-10-30) — Q6, Q7, Q8

### Commands and results

```
.venv/Scripts/python -m pytest -q
61 passed, 1 warning in 8.20s

.venv/Scripts/ruff check .
All checks passed!
```

Wheel contents (built with `pip wheel . --no-deps`):

```
xliff_mcp/schemas/xliff-core-1.2-strict.xsd
```

### Q8 evidence

`get_safe_xml_parser` fetched from `raw.githubusercontent.com/translate/translate/<tag>/translate/misc/xml_helpers.py` for tags 3.19.0, 3.19.1, 3.19.2, 3.19.3 (absent) and 3.19.4 (present). `pyproject.toml` now requires `translate-toolkit>=3.20.1`. No other version was installed or run.

### Q6 evidence

`schema_check` on the real export: `valid: True`, `error_count: 0`, ignored `x-state-qualifier`, `{SmartcatXliff}last-modified-date`, `{SmartcatXliff}last-modified-user`, `{SmartcatXliff}locked`, `{SmartcatXliff}match-quality`. On plain fixtures: valid with nothing ignored. On a document missing `<source>` or carrying `state="bogus"`: invalid.

### Q7 evidence

Six tests cover: `segNumber` addressing across two `<file>` elements that both use ids `1` and `2`; two translations for duplicate id `1` filling the first and third units; one translation touching a single unit; the report flagging duplicates and id reordering.

### Regression

Re-running the real fill after the Q7 rewrite produced a byte-identical file:

```
580dc6f6ff35f495ae44fa33e751edfe *out/filled-en-ar.xliff   (before)
580dc6f6ff35f495ae44fa33e751edfe *out/filled-en-ar.xliff   (after)
```

### Not run

- No test against translate-toolkit 3.19.4–3.20.0.
- No schema validation of SDLXLIFF beyond the existing `SDL_XLIFF` sample (which passes with `sdl:seg-defs` ignored).

## Step 7 (2026-10-30) — independent review reproduced and answered

Every finding in `review-findings.md` was reproduced before being fixed. Reproduction script `/tmp/verify_argon.py`, output before the fixes:

```
#1 both keys        count: 2 | targets: ['غاما', '', 'غاما']
#2 duplicate ids    [(1,'1','Alpha'), (2,'2','Beta'), (3,'1','Alpha')]
#3 lt round trip    target: 1 &lt; 2 &lt;g id="1"&gt;text&lt;/g&gt;   (tags destroyed)
#4 malformed tags   '</g/>' -> '</g/>' ... validate_xliff False for all four
#5 entity           RAISED: XMLSchemaValidateError
#7 sc:state         <target sc:state="translated" state="needs-translation">
#6 alt-trans        <target state="translated">نص</target> written INSIDE <alt-trans>
```

After the fixes, same script:

```
#1 count: 1 | targets: ['', '', 'غاما']
#2 [(1,'1','Alpha'), (2,'2','Beta'), (3,'1','Gamma')]
#3 target: 1 &lt; 2 <g id="1">text</g>    valid: True
#4 all four escaped, valid=True
#5 {'valid': False, 'errors': ['schema validation failed: ...']}
#7 <target sc:state="locked" state="translated">
#6 <target state="translated">نص</target> before <alt-trans> ... untouched inside
```

### Commands and results

```
.venv/Scripts/python -m pytest -q
76 passed, 1 warning in 5.17s

.venv/Scripts/ruff check .
All checks passed!
```

Real-file regression after the renderer rewrite:

```
580dc6f6ff35f495ae44fa33e751edfe *out/filled-en-ar.xliff   (unchanged)
```

### Not run

- No test against an `<alt-trans>` that also contains inline tags.
- ~~No history rewrite~~ — done after Step 7: `git filter-branch` and a force-push removed the identifiers from every commit (see the entry in `changelog.md`).

## Step 8 (2026-10-30) — second review round

Reproduced with `/tmp/verify_argon2.py` before the fixes:

```
#3 tag attribute   extracted: x <ph id="1" equiv-text="A & B"/> y      (unescaped inside the tag)
                   target:    x &lt;ph id="1" equiv-text="A &amp; B"/&gt; y   (tag escaped away)
#4 closing tag     rendered: <g id="1">hello</g id="1">   -> validate_xliff False
#6a alt-trans only target: 'old'  -> diff_report reports "target attributes changed"
#6b self-closing    target: '<alt-trans><source>s</source><target>old'
#10 process_xliff  [(1,'ar'), (2,'ar'), (3,'ar')] for a file whose third unit is in a fa file
```

After:

```
#3 extracted/target: x <ph id="1" equiv-text="A &amp; B"/> y , valid True
#4 rendered: &lt;g id="1"&gt;hello&lt;/g id="1"&gt; , valid True
#6a target '' and diff_report issues []
#6b target ''
#10 [(1,'ar'), (2,'ar'), (3,'fa')]
```

### Commands and results

```
.venv/Scripts/python -m pytest -q              82 passed, 1 warning
.venv/Scripts/ruff check .                     All checks passed!
.venv/Scripts/ruff format --check tests/ xliff_mcp/
    12 files would be reformatted, 12 files already formatted
```

The 12 unformatted files are pre-existing; the three new test files were formatted in this step. `xliff_mcp/xliff_processor.py` remains deliberately unformatted (see Step 3).

Real-file regression: `md5 580dc6f6ff35f495ae44fa33e751edfe` — unchanged.

### Not run

- No test of `<alt-trans>` nested inside `<group>`.
- No test of an inline tag whose attribute value contains a literal `>`.
