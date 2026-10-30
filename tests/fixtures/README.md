# Fixtures

All files here are synthetic or anonymised. None contains customer data.

- `smartcat-en-ar.xliff` — English→Arabic export in Smartcat's shape: XLIFF 1.2 default namespace plus `xmlns:sc="SmartcatXliff"`, one `<file>`, 183 `<trans-unit>`, `xml:space="preserve"` on every source and target, `state` on every target, and `ctype="x-smartcat"` inline tags (`<x>` and `<g>` only). Derived from a real export by substituting every company name, person name, identifier, address, notary number and receipt number; element structure, attribute names, tag skeletons and header bytes are unchanged from the original.
- `plain-en-ar.xliff` — hand-written XLIFF 1.2, no `sc:` namespace. Covers a tagged segment (`<x>` + `<g>`), an escaped ampersand in source, a pre-translated target, and a segment whose significant whitespace must survive extraction.
- `plain-en-fa.xliff` — hand-written XLIFF 1.2 for Persian: Persian-Indic digits, a ZWNJ, a Latin term, and one inline `<x>`.

SDLXLIFF fixtures are deliberately absent: SDLXLIFF is out of scope (`docs/review/open-questions.md`, Q1).
