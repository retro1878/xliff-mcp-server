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
