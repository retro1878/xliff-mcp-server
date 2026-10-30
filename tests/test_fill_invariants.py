"""Invariants for filling <target> in Smartcat XLIFF 1.2 exports.

Scope: `.xliff` produced by Smartcat (default XLIFF 1.2 namespace, `sc:` extension
namespace, `xml:space="preserve"`, `state` on every target). SDLXLIFF is out of
scope by decision recorded in docs/review/open-questions.md (Q1).

Each test states one invariant from the task. `assert_output_invariants` is the
whole contract in one place; the meta-tests at the bottom feed it deliberately
broken documents to prove it actually catches violations.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from lxml import etree

from xliff_mcp.xliff_processor import XliffProcessorService

FIXTURES = Path(__file__).parent / "fixtures"
SMARTCAT = FIXTURES / "smartcat-en-ar.xliff"
PLAIN_AR = FIXTURES / "plain-en-ar.xliff"
PLAIN_FA = FIXTURES / "plain-en-fa.xliff"

XLF_NS = "urn:oasis:names:tc:xliff:document:1.2"
NS = {"x": XLF_NS}

TARGET_RE = re.compile(r"<target\b[^>]*/>|<target\b[^>]*>.*?</target>", re.S)
SOURCE_RE = re.compile(r"<source\b[^>]*>.*?</source>", re.S)
UNIT_RE = re.compile(r"<trans-unit\b.*?</trans-unit>", re.S)
TARGET_OPEN_RE = re.compile(r"<target\b[^>]*>")
TAG_RE = re.compile(r"<(/?)([A-Za-z][\w:.-]*)((?:[^<>\"']|\"[^\"]*\"|'[^']*')*?)(/?)>")

INLINE = {"g", "bpt", "ept", "ph", "it", "mrk", "x", "bx", "ex"}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def units(xml: str) -> list[str]:
    return UNIT_RE.findall(xml)


def mask_targets(xml: str) -> str:
    """Blank every <target> element (content and attributes)."""
    return TARGET_RE.sub("<target/>", xml)


def unit_id(unit: str) -> str:
    return re.search(r'<trans-unit\b[^>]*\bid="([^"]+)"', unit).group(1)


def target_open(unit: str) -> str:
    return TARGET_OPEN_RE.search(unit).group(0)


def normalize_tag(tag: str) -> str:
    """Drop the state attribute and collapse whitespace, so only the attribute
    set (and its order) is compared."""
    tag = re.sub(r'\sstate="[^"]*"', "", tag)
    return re.sub(r"\s+", " ", tag).replace(" >", ">")


def tag_skeleton(fragment: str) -> list[tuple[str, str]]:
    """(localname, id) for each opening or self-closing inline tag, in order."""
    out = []
    for closing, name, attrs, _ in TAG_RE.findall(fragment):
        local = name.split(":")[-1]
        if closing or local not in INLINE:
            continue
        id_match = re.search(r'\bid="([^"]*)"', attrs)
        out.append((local, id_match.group(1) if id_match else ""))
    return out


def inner(xml: str, unit: str, element: str) -> str:
    match = re.search(rf"<{element}\b[^>]*>(.*?)</{element}>", unit, re.S)
    return match.group(1) if match else ""


def text_of(fragment: str) -> str:
    """Text content of an XML fragment, tags stripped."""
    root = etree.fromstring(f"<r>{fragment}</r>")
    return "".join(root.itertext())


def fill(content: str, translations: list[dict]) -> tuple[str, int]:
    return XliffProcessorService.replace_xliff_targets(content, translations)


def assert_output_invariants(
    original: str,
    filled: str,
    filled_ids: set[str],
    *,
    expect_state: str = "translated",
) -> None:
    """The full contract. Raises AssertionError naming the broken invariant."""
    orig_units = units(original)
    new_units = units(filled)

    # 1. Segment count in == segment count out.
    assert len(orig_units) == len(new_units), (
        f"unit count changed: {len(orig_units)} -> {len(new_units)}"
    )
    assert [unit_id(u) for u in orig_units] == [unit_id(u) for u in new_units], (
        "unit ids changed or reordered"
    )

    # 2. Everything outside <target> is byte-identical (source, ids, attributes,
    #    namespaces, header).
    assert mask_targets(original) == mask_targets(filled), (
        "bytes outside <target> changed"
    )

    # 3. Per unit: source bytes identical; target attributes identical except state.
    for before, after in zip(orig_units, new_units):
        uid = unit_id(before)
        assert SOURCE_RE.findall(before) == SOURCE_RE.findall(after), (
            f"unit {uid}: <source> changed"
        )
        assert normalize_tag(target_open(before)) == normalize_tag(
            target_open(after)
        ), f"unit {uid}: target attributes other than state changed"
        if uid in filled_ids:
            assert f'state="{expect_state}"' in target_open(after), (
                f"unit {uid}: filled target has {target_open(after)!r}, "
                f"expected state={expect_state!r}"
            )
        else:
            assert before == after, f"unit {uid}: unfilled unit was modified"

    # 4. Well-formed and accepted by the project's validator.
    etree.fromstring(filled.encode("utf-8"))
    valid, message, count = XliffProcessorService.validate_xliff(filled)
    assert valid, f"validate_xliff rejected output: {message}"
    assert count == len(orig_units), f"validator counted {count} units"

    # 5. Inline tags in a filled target mirror the source tag skeleton.
    for after in new_units:
        if unit_id(after) in filled_ids:
            assert tag_skeleton(inner(after, after, "target")) == tag_skeleton(
                inner(after, after, "source")
            ), f"unit {unit_id(after)}: inline tags differ from source"


AR_FILL = {
    "1": "المبلغ الإجمالي: 1,250.00 GBP",
    "2": 'صفحة <x id="1" /> من <g id="2">10</g>',
    "3": "الدفع & التسوية",
    "5": "  مُباعد  ",
}

FA_FILL = {
    "1": "موجودی: ۶٬۸۸۹٬۹۹۰٬۷۶۹ ریال",
    "2": 'ثبت‌شده در ACRA<x id="1" /> در ۳۱ ژانویه ۲۰۱۹',
    "3": "وضعیت شرکت",
}


def payload(mapping: dict[str, str]) -> list[dict]:
    return [{"unitId": uid, "aiResult": text} for uid, text in mapping.items()]


# --------------------------------------------------------------------------- #
# invariants on the plain Arabic fixture
# --------------------------------------------------------------------------- #
def test_plain_ar_only_targets_change() -> None:
    original = load(PLAIN_AR)
    filled, count = fill(original, payload(AR_FILL))

    assert count == len(AR_FILL)
    assert_output_invariants(original, filled, set(AR_FILL))


def test_plain_ar_arabic_text_numbers_and_latin_terms_survive() -> None:
    original = load(PLAIN_AR)
    filled, _ = fill(original, payload(AR_FILL))
    doc = etree.fromstring(filled.encode("utf-8"))

    targets = {
        tu.get("id"): "".join(tu.find("x:target", NS).itertext())
        for tu in doc.findall(".//x:trans-unit", NS)
    }
    assert targets["1"] == AR_FILL["1"]
    assert "1,250.00" in targets["1"]
    assert "GBP" in targets["1"]
    # raw ampersand in the payload must come back as text, not break the XML
    assert targets["3"] == AR_FILL["3"]
    # leading/trailing spaces are content when xml:space="preserve"
    assert targets["5"] == AR_FILL["5"]


def test_plain_ar_ampersand_is_escaped_not_written_raw() -> None:
    original = load(PLAIN_AR)
    filled, _ = fill(original, payload(AR_FILL))

    assert "&amp;" in filled
    etree.fromstring(filled.encode("utf-8"))


def test_plain_ar_filled_targets_are_marked_translated() -> None:
    original = load(PLAIN_AR)
    filled, _ = fill(original, payload(AR_FILL))

    for unit in units(filled):
        if unit_id(unit) in AR_FILL:
            assert 'state="translated"' in target_open(unit)
    # the unit that was not in the payload keeps its original state
    untouched = next(u for u in units(filled) if unit_id(u) == "4")
    assert 'state="translated"' in target_open(untouched)
    assert 'state-qualifier="exact-match"' in target_open(untouched)


def test_plain_ar_inline_tags_mirror_source() -> None:
    original = load(PLAIN_AR)
    filled, _ = fill(original, payload(AR_FILL))
    unit = next(u for u in units(filled) if unit_id(u) == "2")

    assert tag_skeleton(inner(unit, unit, "target")) == [("x", "1"), ("g", "2")]
    assert tag_skeleton(inner(unit, unit, "source")) == [("x", "1"), ("g", "2")]


def test_extraction_preserves_significant_whitespace() -> None:
    """xml:space="preserve" makes edge spaces content; extraction must not strip."""
    data = XliffProcessorService.process_xliff_with_tags("f", load(PLAIN_AR))
    by_id = {unit.unitId: unit for unit in data}

    assert by_id["5"].source == " spaced "
    assert by_id["2"].source == 'Page <x id="1" /> of <g id="2">10</g>'


# --------------------------------------------------------------------------- #
# invariants on the Persian fixture
# --------------------------------------------------------------------------- #
def test_plain_fa_persian_text_numbers_and_tags_survive() -> None:
    original = load(PLAIN_FA)
    filled, count = fill(original, payload(FA_FILL))

    assert count == len(FA_FILL)
    assert_output_invariants(original, filled, set(FA_FILL))

    doc = etree.fromstring(filled.encode("utf-8"))
    targets = {
        tu.get("id"): "".join(tu.find("x:target", NS).itertext())
        for tu in doc.findall(".//x:trans-unit", NS)
    }
    assert targets["1"] == FA_FILL["1"]
    assert "۶٬۸۸۹٬۹۹۰٬۷۶۹" in targets["1"]
    assert "ACRA" in targets["2"]
    assert "‌" in targets["2"]  # ZWNJ inside ثبت‌شده
    assert tag_skeleton(inner(filled, units(filled)[1], "target")) == [("x", "1")]


# --------------------------------------------------------------------------- #
# invariants on the Smartcat export
# --------------------------------------------------------------------------- #
def smartcat_translations() -> dict[str, str]:
    """Fill the empty Smartcat units, including every tagged one."""
    return {
        "9216140": "هيئة المحاسبة والتنظيم الإداري للشركات",
        "9216144": "الملف التجاري لشركة NORTHWIND TECHNOLOGIES PTE. LTD. (201900001C)",
        "9216152": 'صفحة <x id="1" ctype="x-smartcat" /> من',
        "9216209": '<g id="1" ctype="x-smartcat">1</g> يتضمن عدد الأسهم عدد أسهم الخزينة',
        "9216278": 'الجنسية<g id="1" ctype="x-smartcat">2 </g>/ <x id="2" ctype="x-smartcat" />مكان المنشأ<g id="3" ctype="x-smartcat">3</g>',
        "9216312": "مسجل الشركات & الأسماء التجارية",
        "9216320": '<g id="1" ctype="x-smartcat">: </g>ACRA260101000000',
    }


def test_smartcat_only_targets_change() -> None:
    original = load(SMARTCAT)
    translations = smartcat_translations()
    filled, count = fill(original, payload(translations))

    assert count == len(translations)
    assert_output_invariants(original, filled, set(translations))


def test_smartcat_header_is_byte_identical() -> None:
    original = load(SMARTCAT)
    filled, _ = fill(original, payload(smartcat_translations()))

    header = re.search(r"<header>.*?</header>", original, re.S).group(0)
    assert header in filled


def test_smartcat_translated_units_keep_their_provenance_attributes() -> None:
    original = load(SMARTCAT)
    filled, _ = fill(original, payload(smartcat_translations()))

    for unit in units(filled):
        if unit_id(unit) in {"9216142", "9216146"}:
            assert 'state-qualifier="exact-match"' in target_open(unit)
            assert 'sc:match-quality="100"' in target_open(unit)


def test_smartcat_tagged_targets_keep_smartcat_ctype() -> None:
    original = load(SMARTCAT)
    filled, _ = fill(original, payload(smartcat_translations()))
    unit = next(u for u in units(filled) if unit_id(u) == "9216278")

    assert inner(unit, unit, "target").count('ctype="x-smartcat"') == 3


# --------------------------------------------------------------------------- #
# meta-tests: the checker must fail on deliberately broken output
# --------------------------------------------------------------------------- #
def unit_sub(xml: str, uid: str, old: str, new: str) -> str:
    """Apply a replacement inside exactly one unit."""

    def repl(match: re.Match[str]) -> str:
        unit = match.group(0)
        return unit.replace(old, new) if unit_id(unit) == uid else unit

    return UNIT_RE.sub(repl, xml)


def test_meta_dropped_tag_is_caught() -> None:
    original = load(PLAIN_AR)
    filled, _ = fill(original, payload(AR_FILL))
    broken = unit_sub(filled, "2", 'من <g id="2">10</g>', "من")

    with pytest.raises(AssertionError, match="inline tags differ"):
        assert_output_invariants(original, broken, set(AR_FILL))


def test_meta_raw_ampersand_is_caught() -> None:
    original = load(PLAIN_AR)
    filled, _ = fill(original, payload(AR_FILL))
    broken = unit_sub(filled, "3", "الدفع &amp; ", "الدفع & ")

    with pytest.raises(etree.XMLSyntaxError):
        assert_output_invariants(original, broken, set(AR_FILL))


def test_meta_touched_source_is_caught() -> None:
    original = load(PLAIN_AR)
    filled, _ = fill(original, payload(AR_FILL))
    broken = unit_sub(filled, "3", "<source>Payment", "<source>Payments")

    with pytest.raises(AssertionError, match="outside <target> changed"):
        assert_output_invariants(original, broken, set(AR_FILL))


def test_meta_missing_state_is_caught() -> None:
    original = load(PLAIN_AR)
    filled, _ = fill(original, payload(AR_FILL))
    broken = unit_sub(filled, "1", 'state="translated"', 'state="needs-translation"')

    with pytest.raises(AssertionError, match="expected state"):
        assert_output_invariants(original, broken, set(AR_FILL))


def test_meta_dropped_unit_is_caught() -> None:
    original = load(PLAIN_AR)
    filled, _ = fill(original, payload(AR_FILL))
    broken = UNIT_RE.sub(
        lambda m: "" if unit_id(m.group(0)) == "5" else m.group(0), filled
    )

    with pytest.raises(AssertionError, match="unit count changed"):
        assert_output_invariants(original, broken, set(AR_FILL))


# --------------------------------------------------------------------------- #
# tag enforcement: the target must mirror the source's inline tags
# --------------------------------------------------------------------------- #
def test_tagless_translation_for_a_tagged_segment_is_skipped() -> None:
    original = load(PLAIN_AR)

    filled, count = fill(original, [{"unitId": "2", "aiResult": "صفحة من"}])

    assert count == 0
    unit = next(u for u in units(filled) if unit_id(u) == "2")
    assert inner(unit, unit, "target") == ""
    assert 'state="needs-translation"' in target_open(unit)


def test_translation_missing_one_tag_is_skipped() -> None:
    original = load(PLAIN_AR)

    filled, count = fill(
        original, [{"unitId": "2", "aiResult": 'صفحة <x id="1" /> من'}]
    )

    assert count == 0
    assert (
        inner(next(u for u in units(filled) if unit_id(u) == "2"), "", "target") == ""
    )


def test_require_tags_false_writes_the_translation_anyway() -> None:
    original = load(PLAIN_AR)

    filled, count = XliffProcessorService.replace_xliff_targets(
        original, [{"unitId": "2", "aiResult": "صفحة من"}], require_tags=False
    )

    assert count == 1
    unit = next(u for u in units(filled) if unit_id(u) == "2")
    assert inner(unit, unit, "target") == "صفحة من"


def test_untagged_source_is_unaffected_by_the_tag_rule() -> None:
    original = load(PLAIN_AR)

    _, count = fill(original, [{"unitId": "1", "aiResult": "المبلغ الإجمالي"}])

    assert count == 1


def test_tool_reports_the_skipped_count() -> None:
    import json

    from xliff_mcp.server import replace_xliff_targets as tool

    result = json.loads(
        tool(load(PLAIN_AR), json.dumps([{"unitId": "2", "aiResult": "صفحة من"}]))
    )

    assert result["replacements_count"] == 0
    assert result["skipped_count"] == 1
    assert "skipped" in result["message"]
