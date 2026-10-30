"""Regression tests for the independent review of 2026-10-30.

Each test names the finding it pins down; see docs/review/review-findings.md.
"""

from __future__ import annotations

import json
import re

from xliff_mcp.server import validate_xliff
from xliff_mcp.xliff_processor import XliffProcessorService, _render_fragment

XLIFF = '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'

TWO_FILES = """<?xml version="1.0" encoding="UTF-8"?>
<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">
  <file original="a" datatype="plaintext" source-language="en" target-language="ar">
    <body>
      <trans-unit id="1"><source>Alpha</source><target state="needs-translation"></target></trans-unit>
      <trans-unit id="2"><source>Beta</source><target state="needs-translation"></target></trans-unit>
    </body>
  </file>
  <file original="b" datatype="plaintext" source-language="en" target-language="fa">
    <body>
      <trans-unit id="1"><source>Gamma</source><target state="needs-translation"></target></trans-unit>
    </body>
  </file>
</xliff>
"""


def one_unit(body: str) -> str:
    return (
        XLIFF
        + '<file original="a" datatype="plaintext" source-language="en" target-language="ar">'
        f'<body><trans-unit id="1">{body}</trans-unit></body></file></xliff>'
    )


def target_of(content: str) -> str:
    return re.search(r"<target[^>]*>(.*?)</target>", content, re.S).group(1)


def targets_of(content: str) -> list[str]:
    return re.findall(r"<target[^>]*>(.*?)</target>", content, re.S)


# 1 -------------------------------------------------------------------------
def test_entry_with_both_keys_fills_only_its_position() -> None:
    filled, count = XliffProcessorService.replace_xliff_targets(
        TWO_FILES, [{"segNumber": 3, "unitId": "1", "aiResult": "غاما"}]
    )

    assert count == 1
    assert targets_of(filled) == ["", "", "غاما"]


# 2 -------------------------------------------------------------------------
def test_with_tags_uses_each_units_own_body_with_duplicate_ids() -> None:
    data = XliffProcessorService.process_xliff_with_tags("two.xliff", TWO_FILES)

    assert [(unit.segNumber, unit.unitId, unit.source) for unit in data] == [
        (1, "1", "Alpha"),
        (2, "2", "Beta"),
        (3, "1", "Gamma"),
    ]


def test_with_tags_reads_languages_from_the_enclosing_file() -> None:
    data = XliffProcessorService.process_xliff_with_tags("two.xliff", TWO_FILES)

    assert [(unit.srcLang, unit.tgtLang) for unit in data] == [
        ("en", "ar"),
        ("en", "ar"),
        ("en", "fa"),
    ]


# 3 -------------------------------------------------------------------------
def test_lt_round_trip_keeps_tags_and_escapes_the_less_than() -> None:
    source = one_unit(
        '<source>1 &lt; 2 <g id="1">text</g></source><target state="needs-translation"></target>'
    )
    extracted = XliffProcessorService.process_xliff_with_tags("x", source)[0].source

    filled, _ = XliffProcessorService.replace_xliff_targets(
        source, [{"unitId": "1", "aiResult": extracted}]
    )

    assert target_of(filled) == '1 &lt; 2 <g id="1">text</g>'
    assert XliffProcessorService.validate_xliff(filled)[0] is True


# 4 -------------------------------------------------------------------------
def test_unusable_tag_candidates_are_escaped_not_written_raw() -> None:
    cases = ["</g/>", '<x id="1 & 2"/>', "<x bogus/>", "<ns:g>hi</ns:g>"]
    for candidate in cases:
        rendered = _render_fragment(candidate)
        document = one_unit(f"<source>s</source><target>{rendered}</target>")
        assert XliffProcessorService.validate_xliff(document)[0] is True, candidate


# 5 -------------------------------------------------------------------------
def test_document_with_an_entity_reference_does_not_raise() -> None:
    content = (
        '<?xml version="1.0"?><!DOCTYPE xliff [<!ENTITY xxe "x">]>'
        + XLIFF
        + '<file original="a" datatype="plaintext" source-language="en"><body>'
        '<trans-unit id="1"><source>&xxe;</source><target></target></trans-unit>'
        "</body></file></xliff>"
    )

    report = XliffProcessorService.schema_check(content)

    assert report["valid"] is False
    assert report["errors"]


def test_validate_tool_survives_the_same_document() -> None:
    content = (
        '<?xml version="1.0"?><!DOCTYPE xliff [<!ENTITY xxe "x">]>'
        + XLIFF
        + '<file original="a" datatype="plaintext" source-language="en"><body>'
        '<trans-unit id="1"><source>&xxe;</source><target></target></trans-unit>'
        "</body></file></xliff>"
    )

    result = json.loads(validate_xliff(content))

    assert "schema_valid" in result


# 6 -------------------------------------------------------------------------
def test_alt_trans_target_is_never_touched() -> None:
    content = one_unit(
        "<source>s</source><alt-trans><source>s</source><target>old</target></alt-trans>"
    )

    filled, _ = XliffProcessorService.replace_xliff_targets(
        content, [{"unitId": "1", "aiResult": "نص"}]
    )

    assert targets_of(filled) == ["نص", "old"]
    assert filled.index('<target state="translated">نص</target>') < filled.index(
        "<alt-trans>"
    )


# 7 -------------------------------------------------------------------------
def test_namespaced_state_attribute_is_not_rewritten() -> None:
    content = one_unit(
        '<source>s</source><target sc:state="locked" state="needs-translation"></target>'
    )

    filled, _ = XliffProcessorService.replace_xliff_targets(
        content, [{"unitId": "1", "aiResult": "نص"}]
    )

    open_tag = re.search(r"<target[^>]*>", filled).group(0)
    assert 'sc:state="locked"' in open_tag
    assert 'state="translated"' in open_tag


# 8 -------------------------------------------------------------------------
def test_diff_report_flags_malformed_output() -> None:
    original = one_unit('<source>s</source><target state="needs-translation"></target>')
    broken = original.replace(
        '<target state="needs-translation"></target>', "<target>a & b</target>"
    )

    report = XliffProcessorService.diff_report(original, broken)

    assert "xml" in {issue["kind"] for issue in report["issues"]}


def test_diff_report_flags_changed_target_attributes() -> None:
    original = one_unit(
        '<source>s</source><target state="needs-translation" xml:space="preserve"></target>'
    )
    broken = original.replace(
        '<target state="needs-translation" xml:space="preserve">',
        '<target state="translated">',
    )

    report = XliffProcessorService.diff_report(original, broken)

    assert "attributes" in {issue["kind"] for issue in report["issues"]}


def test_diff_report_flags_a_pair_turned_into_self_closing() -> None:
    original = one_unit(
        '<source><g id="1">x</g></source><target state="needs-translation"></target>'
    )
    filled = original.replace(
        '<target state="needs-translation"></target>',
        '<target state="translated"><g id="1" /></target>',
    )

    report = XliffProcessorService.diff_report(original, filled)

    assert "tags" in {issue["kind"] for issue in report["issues"]}


def test_diff_report_reports_a_dropped_duplicate_unit_by_id() -> None:
    broken = re.sub(
        r"<trans-unit id=\"1\"><source>Gamma.*?</trans-unit>", "", TWO_FILES, flags=re.S
    )

    report = XliffProcessorService.diff_report(TWO_FILES, broken)

    kinds = [(issue["kind"], issue["detail"]) for issue in report["issues"]]
    assert ("ids", "unit missing from filled file") in kinds
    assert not any(kind == "source" for kind, _ in kinds)


def test_diff_report_flags_a_dropped_ctype() -> None:
    original = one_unit(
        '<source><x id="1" ctype="x-smartcat" /></source><target state="needs-translation"></target>'
    )
    filled = original.replace(
        '<target state="needs-translation"></target>',
        '<target state="translated"><x id="1" /></target>',
    )

    report = XliffProcessorService.diff_report(original, filled)

    assert "tags" in {issue["kind"] for issue in report["issues"]}


# 9 -------------------------------------------------------------------------
def test_attribute_typo_fails_the_schema() -> None:
    content = one_unit(
        '<source stte="x">s</source><target state="needs-translation"></target>'
    )

    report = XliffProcessorService.schema_check(content)

    assert report["valid"] is False


def test_non_xliff_root_is_rejected() -> None:
    report = XliffProcessorService.schema_check("<html><body>hi</body></html>")

    assert report["valid"] is False
    assert "root element" in report["errors"][0]


# Round 2 -------------------------------------------------------------------
def test_tag_attribute_entities_survive_round_trip() -> None:
    source = one_unit(
        '<source>x <ph id="1" equiv-text="A &amp; B"/> y</source>'
        '<target state="needs-translation"></target>'
    )
    extracted = XliffProcessorService.process_xliff_with_tags("x", source)[0].source

    filled, _ = XliffProcessorService.replace_xliff_targets(
        source, [{"unitId": "1", "aiResult": extracted}]
    )

    assert extracted == 'x <ph id="1" equiv-text="A &amp; B"/> y'
    assert target_of(filled) == 'x <ph id="1" equiv-text="A &amp; B"/> y'


def test_closing_tag_with_attributes_is_escaped() -> None:
    rendered = _render_fragment('<g id="1">hello</g id="1">')
    document = one_unit(f"<source>s</source><target>{rendered}</target>")

    assert '<g id="1">' not in rendered
    assert XliffProcessorService.validate_xliff(document)[0] is True


def test_alt_trans_only_target_is_neither_read_nor_reported() -> None:
    source = (
        XLIFF
        + '<file original="a" datatype="plaintext" source-language="en" target-language="ar">'
        '<body><trans-unit id="1"><source>s</source><alt-trans><source>s</source>'
        '<target state="translated" state-qualifier="fuzzy-match">old</target>'
        "</alt-trans></trans-unit></body></file></xliff>"
    )

    assert XliffProcessorService.process_xliff_with_tags("x", source)[0].target == ""

    filled, _ = XliffProcessorService.replace_xliff_targets(
        source, [{"unitId": "1", "aiResult": "نص"}]
    )
    kinds = {
        issue["kind"]
        for issue in XliffProcessorService.diff_report(source, filled)["issues"]
    }
    assert "attributes" not in kinds


def test_self_closing_target_before_alt_trans_is_not_read_as_target() -> None:
    source = (
        XLIFF
        + '<file original="a" datatype="plaintext" source-language="en" target-language="ar">'
        '<body><trans-unit id="1"><source>s</source>'
        '<target state="needs-translation"/>'
        "<alt-trans><source>s</source><target>old</target></alt-trans>"
        "</trans-unit></body></file></xliff>"
    )

    assert XliffProcessorService.process_xliff_with_tags("x", source)[0].target == ""


def test_process_xliff_reads_languages_per_file() -> None:
    assert [
        unit.tgtLang for unit in XliffProcessorService.process_xliff("x", TWO_FILES)
    ] == ["ar", "ar", "fa"]


# Round 3 -------------------------------------------------------------------
def test_self_closing_source_with_alt_trans_is_filled() -> None:
    source = one_unit(
        '<source/><alt-trans><source>Old <g id="1">tag</g></source>'
        "<target>old</target></alt-trans>"
    )

    filled, count = XliffProcessorService.replace_xliff_targets(
        source, [{"unitId": "1", "aiResult": "نص"}]
    )

    assert count == 1
    assert target_of(filled) == "نص"
    assert filled.index('<target state="translated">نص</target>') < filled.index(
        "<alt-trans>"
    )


def test_reordered_placeholders_are_accepted() -> None:
    source = one_unit(
        '<source>From <x id="1"/> to <x id="2"/></source>'
        '<target state="needs-translation"></target>'
    )
    translated = 'إلى <x id="2"/> من <x id="1"/>'

    filled, count = XliffProcessorService.replace_xliff_targets(
        source, [{"unitId": "1", "aiResult": translated}]
    )

    assert count == 1
    assert target_of(filled) == translated


def test_literal_tag_syntax_in_source_text_stays_text() -> None:
    source = one_unit(
        '<source>Write &lt;x id="1"/&gt; in the file</source>'
        '<target state="needs-translation"></target>'
    )
    extracted = XliffProcessorService.process_xliff_with_tags("x", source)[0].source

    filled, count = XliffProcessorService.replace_xliff_targets(
        source, [{"unitId": "1", "aiResult": extracted}]
    )

    assert count == 1
    assert target_of(filled) == 'Write &lt;x id="1"/&gt; in the file'


def test_skipped_units_report_distinct_reasons() -> None:
    source = one_unit(
        '<source>Alpha</source><target state="needs-translation"></target>'
    )

    result = XliffProcessorService.replace_xliff_targets_detailed(
        source,
        [
            {"unitId": "nope", "aiResult": "x"},
            {"segNumber": 1, "unitId": "1", "aiResult": ""},
            {"segNumber": 1, "unitId": "1", "aiResult": "ألفا"},
            {"segNumber": 1, "unitId": "1", "aiResult": "بيتا"},
        ],
    )

    assert result["replacements_count"] == 1
    assert [unit["reason"] for unit in result["skipped_units"]] == [
        "unit_not_found",
        "empty_translation",
        "duplicate_target",
    ]


def test_tag_mismatch_is_reported_as_its_own_reason() -> None:
    source = one_unit(
        '<source><g id="1">x</g></source><target state="needs-translation"></target>'
    )

    result = XliffProcessorService.replace_xliff_targets_detailed(
        source, [{"unitId": "1", "aiResult": "نص"}]
    )

    assert result["replacements_count"] == 0
    assert result["skipped_units"][0]["reason"] == "tags_mismatch"


def test_tool_returns_structured_skips() -> None:
    import json

    from xliff_mcp.server import replace_xliff_targets as tool

    source = one_unit(
        '<source><g id="1">x</g></source><target state="needs-translation"></target>'
    )

    result = json.loads(tool(source, json.dumps([{"unitId": "1", "aiResult": "نص"}])))

    assert result["skipped_count"] == 1
    assert result["skipped_units"] == [
        {"unit_id": "1", "seg_number": None, "reason": "tags_mismatch"}
    ]


# Round 4 -------------------------------------------------------------------
def test_diff_report_after_filling_a_self_closing_source_reports_nothing() -> None:
    source = one_unit(
        '<source/><alt-trans><source>Old <g id="1">tag</g></source>'
        "<target>old</target></alt-trans>"
    )

    filled, count = XliffProcessorService.replace_xliff_targets(
        source, [{"unitId": "1", "aiResult": "نص"}]
    )

    assert count == 1
    assert XliffProcessorService.diff_report(source, filled)["issues"] == []


def test_diff_report_accepts_reordered_placeholders() -> None:
    source = one_unit(
        '<source>From <x id="1"/> to <x id="2"/></source>'
        '<target state="needs-translation"></target>'
    )

    filled, count = XliffProcessorService.replace_xliff_targets(
        source, [{"unitId": "1", "aiResult": 'إلى <x id="2"/> من <x id="1"/>'}]
    )

    assert count == 1
    assert XliffProcessorService.diff_report(source, filled)["issues"] == []


def test_diff_report_still_flags_a_tag_that_changes_shape() -> None:
    source = one_unit(
        '<source><g id="1">x</g></source><target state="needs-translation"></target>'
    )

    filled, _ = XliffProcessorService.replace_xliff_targets(
        source,
        [{"unitId": "1", "aiResult": '<g id="1"/>'}],
        require_tags=False,
    )

    kinds = {
        issue["kind"]
        for issue in XliffProcessorService.diff_report(source, filled)["issues"]
    }
    assert "tags" in kinds
