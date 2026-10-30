"""XLIFF processing service"""

from translate.storage import xliff
from typing import List, Tuple
import html
import logging
import re
import threading
from collections import Counter
from difflib import SequenceMatcher
from functools import lru_cache
from importlib import resources
from xml.sax.saxutils import escape

from lxml import etree

from .models import XliffData

logger = logging.getLogger(__name__)

XLIFF_NAMESPACE = "urn:oasis:names:tc:xliff:document:1.2"
XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
XSD_NAMESPACE = "http://www.w3.org/2001/XMLSchema"
SCHEMA_PATH = "schemas/xliff-core-1.2-strict.xsd"

# One pass over the document; the unit id decides whether it is rewritten.
UNIT_ELEMENT = re.compile(
    r"(<(?:trans-unit|unit)\b[^>]*>)([\s\S]*?)(</(?:trans-unit|unit)>)",
    re.IGNORECASE,
)
TARGET_ELEMENT = re.compile(
    r"<target\b[^>]*?/>|<target\b[^>]*>[\s\S]*?</target>", re.IGNORECASE
)
# Inline elements allowed by XLIFF 1.2 (ElemGroup_TextContent).
INLINE_TAG = re.compile(r"<(/?)([A-Za-z][\w:.-]*)((?:[^<>\"']|\"[^\"]*\"|'[^']*')*?)(/?)>")
INLINE_ELEMENTS = {"g", "bpt", "ept", "ph", "it", "mrk", "x", "bx", "ex"}
XML_SPACE_PRESERVE = re.compile(r"""xml:space\s*=\s*["']preserve["']""", re.IGNORECASE)


class XliffProcessorService:
    """XLIFF file processing service"""
    
    @staticmethod
    def process_xliff(file_name: str, content: str) -> List[XliffData]:
        """
        Parse XLIFF content and extract translation units
        
        Args:
            file_name: File name
            content: XLIFF file content
            
        Returns:
            List of XliffData objects
        """
        try:
            store = xliff.xlifffile()
            store.parse(content.encode('utf-8'))
            
            data = []
            languages = _languages_in_unit_order(content)
            position = -1

            # Get file-level language attributes
            file_src_lang = ""
            file_tgt_lang = ""
            if hasattr(store, 'document') and store.document is not None:
                root = store.document.getroot()
                if root is not None:
                    file_node = root.find('.//{urn:oasis:names:tc:xliff:document:1.2}file')
                    if file_node is None:
                        file_node = root.find('.//file')
                    
                    if file_node is not None:
                        file_src_lang = (file_node.get('source-language') or "").lower()
                        file_tgt_lang = (file_node.get('target-language') or "").lower()
            
            for index, unit in enumerate(store.units):
                if unit.isheader():
                    continue

                position += 1

                unit_full_id = unit.getid()
                if not unit_full_id:
                    continue
                
                # Extract real unit ID
                if '\x04' in unit_full_id:
                    unit_id = unit_full_id.split('\x04')[-1]
                else:
                    unit_id = unit_full_id
                
                # Get translation percentage
                percent = -1
                if hasattr(unit, 'xmlelement'):
                    element = unit.xmlelement
                    percent_value = (
                        element.get('percent') or 
                        element.get('mq:percent') or 
                        element.get('{urn:oasis:names:tc:xliff:document:2.0}percent') or
                        element.get('{urn:oasis:names:tc:xliff:document:1.2}percent')
                    )
                    if percent_value:
                        try:
                            percent = float(percent_value)
                        except ValueError:
                            percent = -1
                
                # Get languages
                src_lang = ""
                tgt_lang = ""
                if hasattr(unit, 'xmlelement'):
                    element = unit.xmlelement
                    src_lang = (element.get('source-language') or "").lower()
                    tgt_lang = (element.get('target-language') or "").lower()
                
                if not src_lang or not tgt_lang:
                    if 0 <= position < len(languages):
                        unit_src_lang, unit_tgt_lang = languages[position]
                    else:
                        unit_src_lang, unit_tgt_lang = file_src_lang, file_tgt_lang
                    if not src_lang:
                        src_lang = unit_src_lang
                    if not tgt_lang:
                        tgt_lang = unit_tgt_lang
                
                xliff_data = XliffData(
                    fileName=file_name,
                    segNumber=index + 1,
                    unitId=unit_id,
                    percent=percent,
                    source=unit.source or "",
                    target=unit.target or "",
                    srcLang=src_lang,
                    tgtLang=tgt_lang
                )
                
                data.append(xliff_data)
            
            return data
            
        except Exception as e:
            logger.error(f"Failed to process XLIFF file: {str(e)}")
            raise
    
    @staticmethod
    def validate_xliff(content: str) -> Tuple[bool, str, int]:
        """
        Validate XLIFF content format
        
        Args:
            content: XLIFF file content
            
        Returns:
            (is_valid, message, unit_count)
        """
        try:
            store = xliff.xlifffile()
            store.parse(content.encode('utf-8'))
            
            unit_count = sum(1 for unit in store.units if not unit.isheader())
            
            return True, "XLIFF format is valid", unit_count
        except Exception as e:
            return False, f"Invalid XLIFF format: {str(e)}", 0

    @staticmethod
    def schema_check(content: str) -> dict:
        """Validate the XLIFF 1.2 core against the OASIS strict schema.

        Vendor extensions are removed before validation and reported back:
        elements and attributes in a foreign namespace, and attributes with no
        namespace that the schema does not declare (Smartcat writes
        `x-state-qualifier` that way). Everything the schema does declare --
        element order, required attributes, `state` enumerations, inline
        element nesting -- is checked.
        """
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        try:
            tree = etree.fromstring(content.encode("utf-8"), parser).getroottree()
        except etree.XMLSyntaxError as error:
            return {
                "valid": False,
                "errors": [str(error)],
                "error_count": 1,
                "ignored_extensions": [],
            }

        if tree.getroot().tag != f"{{{XLIFF_NAMESPACE}}}xliff":
            return {
                "valid": False,
                "errors": [f"root element is {tree.getroot().tag!r}, not an XLIFF 1.2 <xliff>"],
                "error_count": 1,
                "ignored_extensions": [],
            }

        ignored = _strip_extensions(tree)
        ignored_entries = [
            {"name": name, "count": count} for name, count in sorted(ignored.items())
        ]
        schema = _xliff_schema()
        try:
            with _SCHEMA_LOCK:
                valid = schema.validate(tree)
                errors = [f"line {e.line}: {e.message}" for e in schema.error_log]
        except etree.XMLSchemaValidateError as error:
            # e.g. an unresolved entity reference left in the tree.
            return {
                "valid": False,
                "errors": [f"schema validation failed: {error}"],
                "error_count": 1,
                "ignored_extensions": ignored_entries,
            }

        return {
            "valid": valid,
            "errors": errors[:20],
            "error_count": len(errors),
            "ignored_extensions": ignored_entries,
        }

    @staticmethod
    def process_xliff_with_tags(file_name: str, content: str) -> List[XliffData]:
        """
        Process XLIFF preserving internal tags for AI translation

        Args:
            file_name: File name
            content: XLIFF file content

        Returns:
            List of XliffData objects with preserved tags
        """
        try:
            store = xliff.xlifffile()
            store.parse(content.encode('utf-8'))

            # Raw unit bodies in document order: the i-th non-header unit in the
            # store is the i-th <trans-unit> here, which is what keeps repeated
            # ids across <file> elements unambiguous.
            raw_units = [match.group(2) for match in UNIT_ELEMENT.finditer(content)]
            languages = _languages_in_unit_order(content)

            data = []
            unit_index = 0
            raw_index = -1

            for unit in store.units:
                if unit.isheader():
                    continue

                raw_index += 1
                if raw_index >= len(raw_units):
                    break

                unit_index += 1

                unit_full_id = unit.getid()
                if not unit_full_id:
                    continue

                if '\x04' in unit_full_id:
                    unit_id = unit_full_id.split('\x04')[-1]
                else:
                    unit_id = unit_full_id

                percent = -1
                if hasattr(unit, 'xmlelement'):
                    element = unit.xmlelement
                    percent_value = (
                        element.get('percent') or
                        element.get('mq:percent') or
                        element.get('{urn:oasis:names:tc:xliff:document:2.0}percent') or
                        element.get('{urn:oasis:names:tc:xliff:document:1.2}percent')
                    )
                    if percent_value:
                        try:
                            percent = float(percent_value)
                        except ValueError:
                            percent = -1

                # Extract from this unit's own body, never by searching the id.
                raw_unit = raw_units[raw_index]
                source = XliffProcessorService._extract_element_content(raw_unit, 'source')
                target = XliffProcessorService._extract_element_content(raw_unit, 'target')

                if not source:
                    source = unit.source or ""
                if not target:
                    target = unit.target or ""

                src_lang = ""
                tgt_lang = ""
                if hasattr(unit, 'xmlelement'):
                    element = unit.xmlelement
                    src_lang = (element.get('source-language') or "").lower()
                    tgt_lang = (element.get('target-language') or "").lower()

                if not src_lang or not tgt_lang:
                    if raw_index < len(languages):
                        file_src_lang, file_tgt_lang = languages[raw_index]
                    else:
                        file_src_lang, file_tgt_lang = (
                            XliffProcessorService._get_file_languages(content)
                        )
                    if not src_lang:
                        src_lang = file_src_lang
                    if not tgt_lang:
                        tgt_lang = file_tgt_lang

                xliff_data = XliffData(
                    fileName=file_name,
                    segNumber=unit_index,
                    unitId=unit_id,
                    percent=percent,
                    source=source,
                    target=target,
                    srcLang=src_lang,
                    tgtLang=tgt_lang
                )

                data.append(xliff_data)

            return data

        except Exception as e:
            logger.error(f"Failed to process XLIFF with tags: {str(e)}")
            raise

    @staticmethod
    def _extract_element_content(unit_content: str, element_name: str) -> str:
        """Extract an element's inner XML from one trans-unit body."""
        try:
            unit_content, _ = _split_alt_trans(unit_content)
            element_pattern = rf'(<{element_name}[^>]*>)([\s\S]*?)</{element_name}>'

            element_match = re.search(element_pattern, unit_content, re.IGNORECASE)
            if not element_match:
                return ""

            # xml:space="preserve" makes leading/trailing whitespace content.
            content = element_match.group(2)
            if not XML_SPACE_PRESERVE.search(element_match.group(1)):
                content = content.strip()

            return _unescape_text_runs(content)
        except Exception as e:
            logger.error(f"Failed to extract {element_name} content: {str(e)}")
            return ""

    @staticmethod
    def _get_file_languages(xml_content: str) -> Tuple[str, str]:
        """Get language info from file level"""
        try:
            file_pattern = r'<file[^>]*source-language=["\'"]([^"\']*)["\'][^>]*target-language=["\'"]([^"\']*)["\'][^>]*>'
            match = re.search(file_pattern, xml_content, re.IGNORECASE)
            if match:
                return match.group(1).lower(), match.group(2).lower()
            
            file_pattern2 = r'<file[^>]*target-language=["\'"]([^"\']*)["\'][^>]*source-language=["\'"]([^"\']*)["\'][^>]*>'
            match2 = re.search(file_pattern2, xml_content, re.IGNORECASE)
            if match2:
                return match2.group(2).lower(), match2.group(1).lower()
            
            return "", ""
        except Exception:
            return "", ""
    
    @staticmethod
    def replace_xliff_targets(content: str, translations: List[dict]) -> Tuple[str, int]:
        """
        Replace target content in XLIFF file using string replacement

        Only the content of <target> and its state attribute are written; every
        other byte of the document is preserved.

        Args:
            content: Original XLIFF file content
            translations: List of translation data with segNumber, aiResult, mtResult

        Returns:
            (updated_content, replacement_count)
        """
        wanted_by_id: dict[str, list[str]] = {}
        wanted_by_position: dict[int, str] = {}
        for translation in translations:
            new_text = translation.get('aiResult') or translation.get('mtResult')
            if not new_text:
                continue
            unit_id = translation.get('unitId')
            seg_number = translation.get('segNumber')
            # A position wins over an id: with repeated ids across <file>
            # elements the id alone cannot say which unit was meant, and
            # queueing the same text under both keys would fill a second unit.
            if seg_number is not None:
                try:
                    wanted_by_position[int(seg_number)] = new_text
                    continue
                except (TypeError, ValueError):
                    pass
            if unit_id:
                wanted_by_id.setdefault(str(unit_id), []).append(new_text)

        replacements_count = 0
        position = 0

        def rewrite(match: "re.Match[str]") -> str:
            nonlocal replacements_count, position
            position += 1
            unit_start, unit_content, unit_end = match.groups()

            # segNumber is a document-wide position, so it stays correct when the
            # same unit id appears in more than one <file>.
            text = wanted_by_position.get(position)
            if text is None:
                queued = wanted_by_id.get(_unit_id(unit_start) or "")
                if queued:
                    text = queued.pop(0)
            if text is None:
                return match.group(0)

            new_unit_content, changed = _fill_target(
                unit_content, _render_fragment(text)
            )
            if not changed:
                return match.group(0)

            replacements_count += 1
            return unit_start + new_unit_content + unit_end

        updated_content = UNIT_ELEMENT.sub(rewrite, content)
        return updated_content, replacements_count

    @staticmethod
    def diff_report(original: str, filled: str) -> dict:
        """Compare an original and a filled document.

        Reports every unit whose target text changed, and every place where
        unit ids, unit count, source bytes, unit attributes, target state or
        inline tags differ. It never modifies anything and never raises on
        malformed input; it reports what it can see.

        Returns:
            dict with original_unit_count, filled_unit_count, counts_match,
            changed_units (ids), issues (list of {unit_id, kind, detail}).
        """
        original_units = _units_in_order(original)
        filled_units = _units_in_order(filled)
        issues: list[dict] = []

        for label, document in (("original", original), ("filled", filled)):
            problem = _xml_problem(document)
            if problem:
                issues.append(
                    {
                        "unit_id": None,
                        "kind": "xml",
                        "detail": f"{label} is not well-formed XML: {problem}",
                    }
                )

        if len(original_units) != len(filled_units):
            issues.append(
                {
                    "unit_id": None,
                    "kind": "count",
                    "detail": (
                        f"{len(original_units)} units before, "
                        f"{len(filled_units)} after"
                    ),
                }
            )

        original_ids = [unit["id"] for unit in original_units]
        filled_ids = [unit["id"] for unit in filled_units]
        for duplicate_id, count in sorted(Counter(original_ids).items()):
            if count > 1:
                issues.append(
                    {
                        "unit_id": duplicate_id,
                        "kind": "ids",
                        "detail": f"duplicate unit id in original ({count} occurrences)",
                    }
                )

        # Equal counts: compare position by position, which catches reordering
        # and id drift. Different counts: align by id sequence, so duplicate ids
        # do not collapse into one dict entry.
        pairs: list[tuple[dict, dict]] = []
        if len(original_units) == len(filled_units):
            pairs = list(zip(original_units, filled_units))
        else:
            matcher = SequenceMatcher(a=original_ids, b=filled_ids, autojunk=False)
            for opcode, i1, i2, j1, j2 in matcher.get_opcodes():
                same_length = (i2 - i1) == (j2 - j1)
                if opcode == "equal" or (opcode == "replace" and same_length):
                    pairs.extend(zip(original_units[i1:i2], filled_units[j1:j2]))
                    continue
                for unit in original_units[i1:i2]:
                    issues.append(
                        {
                            "unit_id": unit["id"],
                            "kind": "ids",
                            "detail": "unit missing from filled file",
                        }
                    )
                for unit in filled_units[j1:j2]:
                    issues.append(
                        {
                            "unit_id": unit["id"],
                            "kind": "ids",
                            "detail": "unit not present in original",
                        }
                    )

        changed: list[str] = []
        for before, after in pairs:
            unit_id = after["id"] or before["id"] or ""
            if before["id"] != after["id"]:
                issues.append(
                    {
                        "unit_id": unit_id,
                        "kind": "ids",
                        "detail": (
                            "unit id differs at this position: "
                            f"{before['id']!r} -> {after['id']!r}"
                        ),
                    }
                )
                continue
            if before["start_tag"] != after["start_tag"]:
                issues.append(
                    {
                        "unit_id": unit_id,
                        "kind": "attributes",
                        "detail": "trans-unit attributes changed",
                    }
                )
            if before["source"] != after["source"]:
                issues.append(
                    {"unit_id": unit_id, "kind": "source", "detail": "source element changed"}
                )

            old_target = _target_parts(before["content"])
            new_target = _target_parts(after["content"])
            if old_target is None and new_target is None:
                continue
            if new_target is None:
                issues.append(
                    {"unit_id": unit_id, "kind": "target", "detail": "target element removed"}
                )
                continue
            if old_target is not None and _tag_without_state(
                old_target["open"]
            ) != _tag_without_state(new_target["open"]):
                issues.append(
                    {
                        "unit_id": unit_id,
                        "kind": "attributes",
                        "detail": "target attributes changed",
                    }
                )
            if old_target is not None and old_target["inner"] == new_target["inner"]:
                continue

            changed.append(unit_id)
            if new_target["state"] != "translated":
                issues.append(
                    {
                        "unit_id": unit_id,
                        "kind": "state",
                        "detail": f"filled target state is {new_target['state']!r}",
                    }
                )
            source_tags = _tag_skeleton(before["source"])
            target_tags = _tag_skeleton(new_target["inner"])
            if source_tags != target_tags:
                issues.append(
                    {
                        "unit_id": unit_id,
                        "kind": "tags",
                        "detail": f"source {source_tags} != target {target_tags}",
                    }
                )

        return {
            "original_unit_count": len(original_units),
            "filled_unit_count": len(filled_units),
            "counts_match": len(original_units) == len(filled_units),
            "changed_units": changed,
            "issues": issues,
        }


def _unit_id(unit_start_tag: str) -> str | None:
    match = re.search(r"""(?<![\w:-])id\s*=\s*["']([^"']+)["']""", unit_start_tag)
    return match.group(1) if match else None


def _with_translated_state(open_tag: str) -> str:
    """Set state="translated" on a <target> opening tag, keeping other attributes."""
    if re.search(r"(?<![\w:-])state\s*=", open_tag):
        open_tag = re.sub(
            r"""((?<![\w:-])state\s*=\s*)(["'])[^"']*\2""",
            r'\1"translated"',
            open_tag,
            count=1,
        )
    else:
        open_tag = re.sub(
            r"^<target",
            '<target state="translated"',
            open_tag,
            count=1,
            flags=re.IGNORECASE,
        )
    return re.sub(r"\s+>", ">", open_tag)


def _fill_target(unit_content: str, rendered: str) -> Tuple[str, bool]:
    """Write rendered content into the unit's <target>; False if there is none."""
    # <alt-trans> carries its own <source>/<target>; never write into it.
    head, tail = _split_alt_trans(unit_content)

    match = TARGET_ELEMENT.search(head)
    if match:
        element = match.group(0)
        if element.endswith("/>"):
            open_tag = _with_translated_state(element[:-2] + ">")
        else:
            open_tag = _with_translated_state(element[: element.index(">") + 1])
        new_element = open_tag + rendered + "</target>"
        new_head = head[: match.start()] + new_element + head[match.end() :]
        return new_head + tail, True

    # No target yet: place it after seg-source when present, else after source.
    anchor = re.search(r"</seg-source>", head, re.IGNORECASE) or re.search(
        r"</source>", head, re.IGNORECASE
    )
    if anchor is None:
        return unit_content, False

    new_target = _with_translated_state("<target>") + rendered + "</target>"
    position = anchor.end()
    return head[:position] + new_target + head[position:] + tail, True


def _render_fragment(text: str) -> str:
    """Escape text while keeping well-formed XLIFF inline tags.

    Each candidate tag must parse as XML on its own and the kept tags must nest
    correctly. Anything else -- a stray '<' left by html.unescape, an illegal
    attribute, an unclosed or mismatched tag -- stays text and is escaped, so
    the result is always well-formed XML.
    """
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    kept: list[re.Match[str]] = []
    for match in INLINE_TAG.finditer(text):
        closing, name, _, self_closing = match.groups()
        if name.split(":")[-1] not in INLINE_ELEMENTS:
            continue
        if self_closing:
            candidate = f"<r>{match.group(0)}</r>"
        elif closing:
            if not re.fullmatch(rf"</\s*{re.escape(name)}\s*>", match.group(0)):
                continue
            candidate = f"<r><{name}></{name}></r>"
        else:
            candidate = f"<r>{match.group(0)}</{name}></r>"
        try:
            etree.fromstring(candidate, parser)
        except etree.XMLSyntaxError:
            continue
        kept.append(match)

    stack: list[str] = []
    for match in kept:
        closing, name, _, self_closing = match.groups()
        if self_closing:
            continue
        if closing:
            if not stack or stack.pop() != name:
                return escape(text)
        else:
            stack.append(name)
    if stack:
        return escape(text)

    parts: list[str] = []
    position = 0
    for match in kept:
        parts.append(escape(text[position : match.start()]))
        parts.append(match.group(0))
        position = match.end()
    parts.append(escape(text[position:]))
    return "".join(parts)


SOURCE_ELEMENT = re.compile(r"<source\b[^>]*>[\s\S]*?</source>", re.IGNORECASE)


def _split_alt_trans(unit_content: str) -> tuple[str, str]:
    """Split a trans-unit body at <alt-trans>: (before, from alt-trans on)."""
    parts = re.split(r"(?=<alt-trans\b)", unit_content, maxsplit=1, flags=re.IGNORECASE)
    return (parts[0], parts[1]) if len(parts) > 1 else (unit_content, "")


def _unescape_text_runs(fragment: str) -> str:
    """html.unescape the text only; tag attributes keep their entities."""
    parts = re.split(r"(<[^<>]*>)", fragment)
    return "".join(part if part.startswith("<") else html.unescape(part) for part in parts)


def _attribute_value(tag: str, name: str) -> str:
    """Value of an unqualified attribute inside a start tag, lowercased."""
    match = re.search(rf"""(?<![\w:-]){re.escape(name)}\s*=\s*["']([^"']*)["']""", tag)
    return match.group(1).strip().lower() if match else ""


def _languages_in_unit_order(xml_content: str) -> list[tuple[str, str]]:
    """(source-language, target-language) per trans-unit, taken from the <file>
    that encloses each one, in document order."""
    languages: list[tuple[str, str]] = []
    file_tags = list(re.finditer(r"<file\b[^>]*>", xml_content, re.IGNORECASE))
    for position, file_tag in enumerate(file_tags):
        end = (
            file_tags[position + 1].start()
            if position + 1 < len(file_tags)
            else len(xml_content)
        )
        block = xml_content[file_tag.end() : end]
        pair = (
            _attribute_value(file_tag.group(0), "source-language"),
            _attribute_value(file_tag.group(0), "target-language"),
        )
        languages.extend([pair] * len(UNIT_ELEMENT.findall(block)))
    return languages


def _units_in_order(xml: str) -> list[dict]:
    """Every trans-unit in document order, including duplicate ids."""
    units: list[dict] = []
    for match in UNIT_ELEMENT.finditer(xml):
        source = SOURCE_ELEMENT.search(match.group(2))
        units.append(
            {
                "id": _unit_id(match.group(1)),
                "start_tag": match.group(1),
                "content": match.group(2),
                "source": source.group(0) if source else "",
            }
        )
    return units


def _target_parts(unit_content: str) -> dict | None:
    unit_content, _ = _split_alt_trans(unit_content)
    match = TARGET_ELEMENT.search(unit_content)
    if not match:
        return None
    element = match.group(0)
    if element.endswith("/>"):
        return {"open": element[:-2] + ">", "inner": "", "state": _state_of(element)}
    open_end = element.index(">")
    open_tag = element[: open_end + 1]
    inner = re.sub(r"</target>\s*$", "", element[open_end + 1 :], flags=re.IGNORECASE)
    return {"open": open_tag, "inner": inner, "state": _state_of(open_tag)}


def _state_of(tag: str) -> str | None:
    match = re.search(r"""(?<![\w:-])state\s*=\s*["']([^"']*)["']""", tag)
    return match.group(1) if match else None


def _tag_without_state(open_tag: str) -> str:
    """An opening tag with its state attribute removed, for comparison."""
    tag = re.sub(
        r"""\s+(?<![\w:-])state\s*=\s*(["'])[^"']*\1""", "", open_tag, count=1
    )
    return re.sub(r"\s+>", ">", tag)


def _xml_problem(document: str) -> str | None:
    """The XMLSyntaxError message if the document does not parse, else None."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    try:
        etree.fromstring(document.encode("utf-8"), parser)
        return None
    except etree.XMLSyntaxError as error:
        return str(error)


def _tag_skeleton(fragment: str) -> list[str]:
    """Inline tag structure: name, id, ctype, self-closing, and close markers."""
    skeleton: list[str] = []
    for closing, name, attrs, self_closing in INLINE_TAG.findall(fragment):
        local = name.split(":")[-1]
        if local not in INLINE_ELEMENTS:
            continue
        if closing:
            skeleton.append(f"/{local}")
            continue
        id_match = re.search(r"""(?<![\w:-])id\s*=\s*["']([^"']*)["']""", attrs)
        ctype_match = re.search(r"""(?<![\w:-])ctype\s*=\s*["']([^"']*)["']""", attrs)
        skeleton.append(
            "{name}[{id}|{ctype}]{self_closing}".format(
                name=local,
                id=id_match.group(1) if id_match else "",
                ctype=ctype_match.group(1) if ctype_match else "",
                self_closing="/" if self_closing else "",
            )
        )
    return skeleton


_SCHEMA_LOCK = threading.Lock()


def _schema_bytes() -> bytes:
    return resources.files(__package__).joinpath(SCHEMA_PATH).read_bytes()


@lru_cache(maxsize=1)
def _xliff_schema() -> etree.XMLSchema:
    """The OASIS XLIFF 1.2 strict schema, compiled once."""
    return etree.XMLSchema(etree.fromstring(_schema_bytes()))


def _strip_extensions(tree: etree._ElementTree) -> dict[str, int]:
    """Remove vendor extensions from a parsed tree, in place.

    Only two shapes are treated as extensions: elements and attributes in a
    foreign namespace, and unqualified attributes prefixed `x-` (Smartcat's
    `x-state-qualifier`). Anything else the schema does not declare -- a typo
    such as `stte=` -- is left in place so validation fails on it.

    Returns {"{namespace}name" or "x-name": occurrences} for what was removed.
    """
    ignored: dict[str, int] = {}
    for element in list(tree.iter()):
        if not isinstance(element.tag, str):
            continue
        if element.tag.startswith("{"):
            if element.tag.startswith(f"{{{XLIFF_NAMESPACE}}}"):
                pass
            else:
                ignored[element.tag] = ignored.get(element.tag, 0) + 1
                parent = element.getparent()
                if parent is not None:
                    parent.remove(element)
                continue
        for name in list(element.attrib):
            if name.startswith("{"):
                if name.startswith(f"{{{XLIFF_NAMESPACE}}}") or name.startswith(
                    f"{{{XML_NAMESPACE}}}"
                ):
                    continue
            elif not name.lower().startswith("x-"):
                continue
            ignored[name] = ignored.get(name, 0) + 1
            del element.attrib[name]
    return ignored
