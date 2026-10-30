"""Q7: unit ids that repeat across <file> elements.

XLIFF only requires ids to be unique within a file. Filling by `segNumber`
(document-wide position) must stay correct when ids repeat; filling by
`unitId` alone must fill one occurrence at a time, in order.
"""

from __future__ import annotations

from xliff_mcp.xliff_processor import XliffProcessorService

TWO_FILES = """<?xml version="1.0" encoding="UTF-8"?>
<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">
  <file original="a" datatype="plaintext" source-language="en" target-language="ar">
    <body>
      <trans-unit id="1"><source>Alpha</source><target state="needs-translation"></target></trans-unit>
      <trans-unit id="2"><source>Beta</source><target state="needs-translation"></target></trans-unit>
    </body>
  </file>
  <file original="b" datatype="plaintext" source-language="en" target-language="ar">
    <body>
      <trans-unit id="1"><source>Gamma</source><target state="needs-translation"></target></trans-unit>
    </body>
  </file>
</xliff>
"""


def targets(content: str) -> list[str]:
    import re

    return [
        re.search(r"<target[^>]*>(.*?)</target>", unit, re.S).group(1)
        for unit in re.findall(r"<trans-unit\b.*?</trans-unit>", content, re.S)
    ]


def test_seg_number_addresses_the_document_position() -> None:
    filled, count = XliffProcessorService.replace_xliff_targets(
        TWO_FILES,
        [
            {"segNumber": 1, "aiResult": "ألفا"},
            {"segNumber": 2, "aiResult": "بيتا"},
            {"segNumber": 3, "aiResult": "غاما"},
        ],
    )

    assert count == 3
    assert targets(filled) == ["ألفا", "بيتا", "غاما"]


def test_duplicate_id_fills_the_first_occurrence_then_the_next() -> None:
    filled, count = XliffProcessorService.replace_xliff_targets(
        TWO_FILES,
        [
            {"unitId": "1", "aiResult": "ألفا"},
            {"unitId": "1", "aiResult": "غاما"},
        ],
    )

    assert count == 2
    assert targets(filled) == ["ألفا", "", "غاما"]


def test_single_translation_for_a_duplicate_id_touches_one_unit() -> None:
    filled, count = XliffProcessorService.replace_xliff_targets(
        TWO_FILES, [{"unitId": "1", "aiResult": "ألفا"}]
    )

    assert count == 1
    assert targets(filled) == ["ألفا", "", ""]


def test_diff_report_flags_duplicate_ids() -> None:
    report = XliffProcessorService.diff_report(TWO_FILES, TWO_FILES)

    duplicate_issues = [
        issue for issue in report["issues"] if "duplicate unit id" in issue["detail"]
    ]
    assert [issue["unit_id"] for issue in duplicate_issues] == ["1"]


def test_diff_report_compares_duplicates_by_position() -> None:
    filled, _ = XliffProcessorService.replace_xliff_targets(
        TWO_FILES,
        [{"segNumber": 1, "aiResult": "ألفا"}, {"segNumber": 3, "aiResult": "غاما"}],
    )

    report = XliffProcessorService.diff_report(TWO_FILES, filled)

    assert report["changed_units"] == ["1", "1"]
    assert {
        issue["kind"]
        for issue in report["issues"]
        if "duplicate" not in issue["detail"]
    } == set()


def test_reordered_units_are_flagged() -> None:
    import re

    single_file = TWO_FILES.split("<file", 2)[1]
    single_file = "<file" + single_file
    first_unit = re.search(
        r'<trans-unit id="1">.*?</trans-unit>', single_file, re.S
    ).group(0)
    second_unit = re.search(
        r'<trans-unit id="2">.*?</trans-unit>', single_file, re.S
    ).group(0)
    swapped = (
        single_file.replace(first_unit, "@@1@@")
        .replace(second_unit, first_unit)
        .replace("@@1@@", second_unit)
    )

    report = XliffProcessorService.diff_report(single_file, swapped)

    assert any(
        "differs at this position" in issue["detail"] for issue in report["issues"]
    )
