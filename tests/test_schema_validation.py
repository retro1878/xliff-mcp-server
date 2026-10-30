"""Q6: schema validation for validate_xliff.

`valid` keeps its old meaning (well-formed and parseable as XLIFF). The schema
answer is reported separately so a vendor extension cannot turn a real Smartcat
export invalid, while a genuinely malformed document still fails.
"""

from __future__ import annotations

import json

from xliff_mcp.server import validate_xliff
from xliff_mcp.xliff_processor import XliffProcessorService

from tests.samples import SAMPLE_XLIFF
from tests.test_fill_invariants import PLAIN_AR, PLAIN_FA, SMARTCAT, load


def test_smartcat_export_is_schema_valid_after_ignoring_extensions() -> None:
    report = XliffProcessorService.schema_check(load(SMARTCAT))

    assert report["valid"] is True
    assert report["errors"] == []
    ignored = {entry["name"] for entry in report["ignored_extensions"]}
    assert "x-state-qualifier" in ignored
    assert "{SmartcatXliff}locked" in ignored


def test_plain_fixtures_need_no_extensions_ignored() -> None:
    for path in (PLAIN_AR, PLAIN_FA):
        report = XliffProcessorService.schema_check(load(path))
        assert report["valid"] is True
        assert report["ignored_extensions"] == []


def test_sample_xliff_is_schema_valid() -> None:
    assert XliffProcessorService.schema_check(SAMPLE_XLIFF)["valid"] is True


def test_missing_source_element_fails_the_schema() -> None:
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        '<file original="a" datatype="plaintext" source-language="en">'
        '<body><trans-unit id="1"><target>x</target></trans-unit></body>'
        "</file></xliff>"
    )

    report = XliffProcessorService.schema_check(content)

    assert report["valid"] is False
    assert report["error_count"] > 0


def test_invalid_state_value_fails_the_schema() -> None:
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        '<file original="a" datatype="plaintext" source-language="en">'
        '<body><trans-unit id="1"><source>x</source>'
        '<target state="bogus">y</target></trans-unit></body>'
        "</file></xliff>"
    )

    report = XliffProcessorService.schema_check(content)

    assert report["valid"] is False


def test_malformed_xml_is_reported_not_raised() -> None:
    report = XliffProcessorService.schema_check("<xliff><file>")

    assert report["valid"] is False
    assert report["errors"]


def test_validate_tool_reports_both_answers() -> None:
    result = json.loads(validate_xliff(load(SMARTCAT)))

    assert result["valid"] is True
    assert result["unit_count"] == 183
    assert result["schema_valid"] is True
    assert result["ignored_extensions"]
