"""Tests for the post-replacement diff report."""

from __future__ import annotations

import json

from xliff_mcp.server import diff_xliff_report, get_server_info, replace_xliff_targets
from xliff_mcp.xliff_processor import XliffProcessorService

from tests.test_fill_invariants import (
    AR_FILL,
    PLAIN_AR,
    SMARTCAT,
    fill,
    load,
    payload,
    smartcat_translations,
    unit_id,
    unit_sub,
    units,
)


def report_of(original: str, filled: str) -> dict:
    return XliffProcessorService.diff_report(original, filled)


def kinds(report: dict, unit: str | None = None) -> list[str]:
    return [
        issue["kind"]
        for issue in report["issues"]
        if unit is None or issue["unit_id"] == unit
    ]


def test_clean_fill_reports_no_issues() -> None:
    original = load(PLAIN_AR)
    filled, _ = fill(original, payload(AR_FILL))

    report = report_of(original, filled)

    assert report["counts_match"] is True
    assert report["original_unit_count"] == report["filled_unit_count"] == 5
    assert report["issues"] == []
    assert sorted(report["changed_units"]) == ["1", "2", "3", "5"]


def test_smartcat_fill_reports_no_issues() -> None:
    original = load(SMARTCAT)
    translations = smartcat_translations()
    filled, _ = fill(original, payload(translations))

    report = report_of(original, filled)

    assert report["issues"] == []
    assert sorted(report["changed_units"]) == sorted(translations)
    assert report["original_unit_count"] == 183


def test_identical_documents_report_nothing() -> None:
    original = load(SMARTCAT)
    report = report_of(original, original)

    assert report["changed_units"] == []
    assert report["issues"] == []


def test_dropped_tag_is_flagged() -> None:
    original = load(PLAIN_AR)
    filled, _ = fill(original, payload(AR_FILL))
    broken = unit_sub(filled, "2", 'من <g id="2">10</g>', "من")

    report = report_of(original, broken)

    assert "tags" in kinds(report, "2")
    assert "2" in report["changed_units"]


def test_missing_state_is_flagged() -> None:
    original = load(PLAIN_AR)
    filled, _ = fill(original, payload(AR_FILL))
    broken = unit_sub(filled, "1", 'state="translated"', 'state="needs-translation"')

    report = report_of(original, broken)

    assert "state" in kinds(report, "1")


def test_changed_source_is_flagged() -> None:
    original = load(PLAIN_AR)
    filled, _ = fill(original, payload(AR_FILL))
    broken = unit_sub(filled, "3", "<source>Payment", "<source>Payments")

    report = report_of(original, broken)

    assert "source" in kinds(report, "3")


def test_changed_unit_attributes_are_flagged() -> None:
    original = load(PLAIN_AR)
    filled, _ = fill(original, payload(AR_FILL))
    broken = unit_sub(filled, "1", 'approved="no"', 'approved="yes"')

    report = report_of(original, broken)

    assert "attributes" in kinds(report, "1")


def test_dropped_unit_is_flagged_as_count_and_id() -> None:
    original = load(PLAIN_AR)
    filled, _ = fill(original, payload(AR_FILL))
    broken = "".join(u for u in units(filled) if unit_id(u) != "5")

    report = report_of(original, broken)

    assert report["counts_match"] is False
    assert report["filled_unit_count"] == 4
    assert "count" in kinds(report)
    assert "ids" in kinds(report, "5")


def test_tool_returns_the_report() -> None:
    original = load(PLAIN_AR)
    filled, _ = fill(original, payload(AR_FILL))

    result = json.loads(diff_xliff_report(original, filled))

    assert result["success"] is True
    assert result["issues"] == []
    assert sorted(result["changed_units"]) == ["1", "2", "3", "5"]


def test_replace_response_includes_the_report() -> None:
    result = json.loads(replace_xliff_targets(load(PLAIN_AR), json.dumps(payload(AR_FILL))))

    assert result["success"] is True
    assert result["diff_report"]["issues"] == []
    assert result["diff_report"]["counts_match"] is True


def test_server_info_lists_the_new_tool() -> None:
    info = json.loads(get_server_info())

    assert "diff_xliff_report" in info["available_tools"]
