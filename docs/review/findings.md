# Step 1 — Findings

Date: 2026-10-30
Repository: `retro1878/xliff-mcp-server` (fork of `langlink-localization/xliff-mcp-server`), clone at commit `dd909e0`.
Nothing in this file was produced from the upstream README alone; every number below comes from a command recorded here or in `tests.md`.

## 1. Environment the code was read and run in

| Item | Value | How |
| --- | --- | --- |
| Python | 3.14.7 | `python --version` |
| translate-toolkit | 3.20.1 | `importlib.metadata.version("translate-toolkit")` |
| lxml | 6.1.3 | `lxml.__version__` |
| mcp | 1.28.1 | `importlib.metadata.version("mcp")` |
| Existing test suite | 21 passed | `.venv/Scripts/python -m pytest -q` |

The declared dependency floors in `pyproject.toml` are `mcp>=1.2.0,<1.29.0`, `translate-toolkit>=3.0.0`, `lxml>=4.9.0`, `pydantic>=2.0.0`. Only the installed versions above were exercised. The behaviour of translate-toolkit 3.0.0 was **not** tested.

## 2. Fixtures — what exists and what does not

There is **no `tests/fixtures/` directory in the fork**, and no `.xliff` or `.sdlxliff` file anywhere in the repository:

```
find . -iname "*fixture*" -o -iname "*.xliff" -o -iname "*.sdlxliff"   # (excluding .git) → no results
```

What does exist is `tests/samples.py`, containing three inline string constants:

- `SAMPLE_XLIFF` — minimal XLIFF 1.2, default namespace `urn:oasis:names:tc:xliff:document:1.2`, two trans-units, one with `<g id="1">` in source and an empty `<target></target>`.
- `SDL_XLIFF` — minimal SDLXLIFF: `xmlns:sdl="http://sdl.com/FileTypes/SdlXliff/1.0"`, `<sdl:seg-defs><sdl:seg id="1" conf="Draft" origin="source"/></sdl:seg-defs>` in the header, `<seg-source><mrk mid="0" mtype="seg">…</mrk></seg-source>`.
- `SAMPLE_TMX` — a TMX 1.4 document (not used by this task).

The one real export supplied for this task was copied to `tests/fixtures/smartcat-acra-en-ar.xliff`:

- Source file: `F-WJ2609578_Apostilled ACRA Biz Profile (20261020)(en-GB-ar).xliff`
- 45,413 bytes, no BOM, **no trailing newline**, single line (no pretty-printing).

## 3. Structure of the Smartcat export

Measured with lxml over the file (`/tmp/measure.py`, output reproduced in `tests.md`).

- Root: `{urn:oasis:names:tc:xliff:document:1.2}xliff`, `version="1.2"`, plus `xmlns:sc="SmartcatXliff"`.
- One `<file>` with attributes `datatype="plaintext"`, `date`, `original`, `source-language="en-GB"`, `target-language="ar"`.
- `<header>` contains a single `<tool tool-name="Smartcat.ai" …/>`. No `<sdl:seg-defs>`, no `<note>`.
- **183** `<trans-unit>` elements, no `<group>`, one `<file>`. All ids unique, numeric strings (`9216140`…`9216322`).
- `trans-unit` attributes used: `id`, `approved="no"`, `sc:locked`, `sc:last-modified-date`, and on five units `sc:last-modified-user`.
- `<source>` always carries `xml:space="preserve"`. Every `<target>` also carries `xml:space="preserve"`.
- Target states: **178** `state="needs-translation"` (all with empty content), **5** `state="translated"` (the five `[Signature]`/`[Logo]` segments filled from TM). The five translated targets additionally carry `state-qualifier="exact-match"`, `x-state-qualifier="x-tm-leveraged-100"` and `sc:match-quality="100"`.
- Inline tags: **11** units contain inline markup, exclusively `ctype="x-smartcat"`:
  - `<x id="1" ctype="x-smartcat" />` — 5 occurrences, self-closing placeholders (page numbers between "Page" and "of", a slash, etc.).
  - `<g id="1" ctype="x-smartcat">…</g>` — 8 occurrences, paired (footnote markers `1`, `2 `, `3`, `: `).
  - No `<bpt>`, `<ept>`, `<ph>`, `<it>`, `<mrk>`, `<bx>`, `<ex>` anywhere.
- Two source segments contain escaped `&amp;`.
- No element carries outer-edge whitespace (first/last character inside `<source>`/`<target>` is non-space), so `.strip()` does not alter this particular file. It would alter a Smartcat export whose segment begins or ends with a space.
- No `<target>` element in this file is self-closing; all are `<target …></target>`.

### XLIFF 1.2 facts checked against the specification

Checked against the OASIS XLIFF 1.2 schema (`xliff-core-1.2-strict.xsd`, downloaded from `docs.oasis-open.org`), not from memory:

- `state` is **optional** on `<target>`; values are `final`, `needs-adaptation`, `needs-l10n`, `needs-review-adaptation`, `needs-review-l10n`, `needs-review-translation`, `needs-translation`, `new`, `signed-off`, `translated`. `translated` = "Indicates that the item has been translated."
- `state-qualifier` is optional; values include `exact-match`, `fuzzy-match`, `mt-suggestion`, `leveraged-tm`, `rejected-*`.
- Inline elements allowed in `<source>`/`<target>` (`ElemGroup_TextContent`): `g`, `bpt`, `ept`, `ph`, `it`, `mrk`, `x`, `bx`, `ex`. The standard `mrk` uses `id`; SDLXLIFF's `mid`/`mtype` are a Trados extension.
- `<target>` content model is mixed content with optional `state`, `state-qualifier`, `phase-name`, `xml:lang`, `resname`, `coord`, `font`, `css-style`, `style`, `exstyle`, `equiv-trans`, plus `##other` attributes — which is why `sc:match-quality` is legal.
- `trans-unit` child order is fixed: `source`, optional `seg-source`, optional `target`, then `context-group`/`count-group`/`note`/`alt-trans`. A `<target>` inserted before `<seg-source>` is schema-invalid.
- `xml:space="preserve"` marks whitespace as significant. `trans-unit`'s default is `xml:space="default"`.

### SDLXLIFF segment state

SDLXLIFF does **not** use `target/@state`; the state lives in `<sdl:seg id="N" conf="…"/>` under `<header><sdl:seg-defs>`. The recognised `conf` values are `Draft`, `Translated`, `ApprovedTranslation`, `RejectedTranslation`, `ApprovedSignOff`, `RejectedSignOff`, and an absent attribute means unspecified. A segment with target text but no `conf="Translated"` is still unconfirmed in Trados. This was taken from RWS Studio API documentation and community sources (see `open-questions.md`); it is not part of the XLIFF 1.2 schema.

## 4. What the server does today

Nine MCP tools, registered for both stdio (`server.py`) and streamable HTTP (`http_server.py`) through one shared `register_tools()` in `xliff_mcp/tool_registry.py:40`:

| Tool | Implementation |
| --- | --- |
| `process_xliff` | translate-toolkit parse; returns `unitId`, `segNumber`, `percent`, `source`, `target`, languages. **Strips all inline tags** from `source`/`target`. |
| `process_xliff_with_tags` | Regex extraction of the raw inner XML of `<source>`/`<target>` per unit id, entities decoded, tags preserved as literal markup. |
| `validate_xliff` | "Can translate-toolkit parse it" plus a unit count. Not schema validation. |
| `replace_xliff_targets` | Regex string surgery on the whole document; returns new content plus a count. |
| `process_tmx`, `validate_tmx`, `export_tmx_file` | TMX equivalents (out of scope for this task). |
| `export_xliff_file` | CSV/JSON of the unit list. |
| `get_server_info` | Self-description. |

Plus four MCP prompts and two resources (`workflows/registry.py`) that only *describe* a workflow to the model; they have no enforcement.

### How `replace_xliff_targets` actually works (`xliff_mcp/xliff_processor.py:279-347`)

1. For each translation, find `<(trans-unit|unit) … id="<unitId>">…</(trans-unit|unit)>` with a case-insensitive regex over the **raw document string**.
2. Find the first `<target …>…</target>` inside that match.
3. Reuse the existing `<target …>` opening-tag attributes verbatim (`:316-318`).
4. Interpolate the translation string **raw** into `<target{attrs}>{new_target_content}</target>` (`:320`).
5. Replace the matched unit text with `str.replace()` over the whole document (`:323-326`).
6. If no `<target>` exists, insert `<target>…</target>` directly after `</source>` (`:330-345`).

`process_xliff_with_tags` is the read side of the same contract (`:131-246`): it locates the unit by id with a regex, takes the first `<source>`/`<target>`, `.strip()`s it (`:239`), then decodes `&amp; &lt; &gt; &quot; &#39; &nbsp;` (`:241`, `:269-274`).

## 5. What it does not handle

All of the following were reproduced with the scripts in `tests.md`, not inferred.

1. **XML escaping on the write path.** A translation containing `&` is written raw. `"… & أخرى"` produced `xmlParseEntityRef: no name` and `validate_xliff` then returned `(False, 'Invalid XLIFF format: xmlParseEntityRef: no name…', 0)`. The read path decodes entities (`:269-274`), so the round trip `extract → translate → replace` corrupts any segment containing `&`, `<`, or `>`.
2. **Segment state is never updated.** Step 3 copies the existing target opening tag verbatim, so a filled target keeps `state="needs-translation"`. On the Smartcat fixture a filled unit came back as `<target state="needs-translation" xml:space="preserve">هيئة المحاسبة…</target>`.
3. **SDLXLIFF structure is destroyed on write.** On `SDL_XLIFF`, replacing unit `1` produced `<target>مرحبا</target>` — the `<mrk mid="0" mtype="seg">` wrapper from `seg-source` was dropped, so the target no longer mirrors the segment structure Trados expects. `process_xliff_with_tags` *does* return the `<mrk>` wrapper in `target` (it is raw inner XML), so the loss happens only if the caller sends plain text.
4. **SDLXLIFF segment state is never touched.** `<sdl:seg conf="Draft">` remains `Draft` after a fill, i.e. the segment stays unconfirmed in Trados.
5. **Whitespace.** `_extract_element_content` strips the element's outer whitespace (`:239`) even though `xml:space="preserve"` makes it significant. Not observable on the supplied fixture (0 elements have outer-edge whitespace) but wrong for other exports.
6. **`<target/>` self-closing.** The target regex requires an explicit `</target>`; a self-closing target falls through to the "insert after source" branch, which would leave the original empty `<target/>` in place and add a second one.
7. **Target insertion ignores schema order.** The inserted `<target>` goes immediately after `</source>`, i.e. before `<seg-source>` — schema-invalid for SDLXLIFF and any XLIFF with segmented units.
8. **Global `.replace()`.** Replacement is by substring over the whole document, so identical serialized units (possible across multiple `<file>` elements) are all rewritten while the count increases once. Duplicate `id`s across files are also ambiguous: extraction takes the first match document-wide.
9. **Multi-file / multi-unit documents** are not distinguished: no `file`-scoped id resolution, and `_get_file_languages` (`:249-264`) only reads the first `<file>` and only if `source-language` and `target-language` appear in one of two orders.
10. **`validate_xliff` is not schema validation.** It returns "valid" for any document translate-toolkit can parse. A deliberately malformed XLIFF that parses will pass. It also reported `True` for a document carrying a DOCTYPE with an external entity (`/tmp/probe4.py`).
11. **No size limit** on `content` in either transport (`grep` for `len(content)` / `max_size` finds nothing). The HTTP transport can be public when no API key is set (`http_server.py:114-117` logs a warning and keeps serving).
12. `percent` is always `-1` for this fixture — it reads a `<trans-unit percent>` attribute that Smartcat does not emit. Not used by replacement; recorded so nobody expects it to work.
13. `unit.target` from `process_xliff` (non-tag path) is translate-toolkit's normalized text, and inline tags are gone (`Page <x/> of` → `Page  of`). Callers must use `process_xliff_with_tags`.

## 6. lxml configuration (asked specifically)

The package never imports lxml. `grep -rn "import lxml\|from lxml" --include=*.py` over the repository (excluding `.venv`) returns nothing; `lxml` is declared in `pyproject.toml` but used only transitively through translate-toolkit.

Parsing goes `xliff_mcp/xliff_processor.py:28-29` → `translate.storage.xliff.xlifffile.parse()` → `translate/storage/lisa.py:633` → `translate.misc.xml_helpers.parse_xml()`, which builds the parser at `xml_helpers.py:53-63` with:

```python
etree.XMLParser(
    collect_ids=collect_ids,
    encoding=encoding,
    strip_cdata=strip_cdata,
    resolve_entities=False,
    no_network=True,
)
```

Consequences, measured in `/tmp/probe4.py` with this environment:

- **External entity (XXE)**: a document with `<!ENTITY xxe SYSTEM "file:///C:/Windows/win.ini">` parsed as "valid"; the text of the entity was **not** substituted (`unit.source` came back as `''`). So no file content is read with translate-toolkit 3.20.1.
- **Entity expansion / billion laughs**: a four-level entity bomb parsed as "valid" without expansion. With `resolve_entities=False` entities are not expanded at all.
- `huge_tree` is **not** set, so lxml's default (off) applies and a single text node above ~10 MB is rejected rather than ballooning memory.
- `no_network=True` blocks network fetches from DTDs.
- **Caveat:** all of the above is a property of translate-toolkit 3.20.1. The project pins only `translate-toolkit>=3.0.0`; whether 3.0.0 uses the same safe parser was not checked. If a floor bump is desired it is a dependency decision for the owner, not something to change unasked.
- The code passes `content.encode("utf-8")` into a parser with `encoding=None`, so the XML declaration is trusted for encoding. A `str` content that was decoded correctly round-trips; a file declaring a non-UTF-8 encoding would be mis-parsed.

## 7. Risks, ranked

1. **Data corruption on write** — unescaped `&`/`<`/`>` produces a file Smartcat cannot import (reproduced). This is the top risk because it is silent: `replace_xliff_targets` returns `success: true` with a broken document.
2. **Silent state loss** — filled targets keep `state="needs-translation"` (Smartcat) or `conf="Draft"` (Trados). If the importer honours state, the whole run is accepted as untranslated.
3. **SDLXLIFF target structure loss** — dropping `<mrk mid mtype>` breaks the segment pairing in Trados and possibly makes the file unopenable.
4. **Translation text becoming markup** — the write path interpolates a caller-supplied string as XML. A translation containing `</target>` or `<trans-unit id="…">` can corrupt or restructure the document. Escaping fixes the common case; structural verification (the Step 4 diff report) is what catches the rest.
5. **Security, HTTP transport** — public-when-unkeyed, unbounded input size, and no schema validation. Not exploited here, but the exposure exists in the upstream design.
6. **Dependency floor vs. verified behaviour** — the XXE result above is version-specific.

## 8. What is out of scope for this task

- TMX handling, CSV/JSON export, auth and rate limiting, HTTP transport, the skills/prompts module: read for context, not changed unless a change is forced by the target work.
- Any rewrite of the regex approach. The instruction is to extend the existing code; the plan is to keep the regex surgery, but make the extracted/written fragment safe and state-aware.

## 9. Open items are tracked in `open-questions.md`

The two that block Step 2 are: (a) SDLXLIFF writes need `<sdl:seg conf>` in the header, which conflicts with the "header stays byte-identical" invariant; (b) whether the real Smartcat fixture may be committed to a public fork.
