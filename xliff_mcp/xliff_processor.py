"""XLIFF processing service"""

from translate.storage import xliff
from typing import List, Tuple
import html
import logging
import re
from xml.sax.saxutils import escape

from .models import XliffData

logger = logging.getLogger(__name__)

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
                
                if not src_lang:
                    src_lang = file_src_lang
                if not tgt_lang:
                    tgt_lang = file_tgt_lang
                
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
            
            data = []
            unit_index = 0
            
            for unit in store.units:
                if unit.isheader():
                    continue
                
                unit_full_id = unit.getid()
                if not unit_full_id:
                    continue
                
                if '\x04' in unit_full_id:
                    unit_id = unit_full_id.split('\x04')[-1]
                else:
                    unit_id = unit_full_id
                
                unit_index += 1
                
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
                
                # Extract content using regex to preserve tags
                source = XliffProcessorService._extract_element_content(content, 'source', unit_id)
                target = XliffProcessorService._extract_element_content(content, 'target', unit_id)
                
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
                    file_src_lang, file_tgt_lang = XliffProcessorService._get_file_languages(content)
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
    def _extract_element_content(xml_content: str, element_name: str, unit_id: str) -> str:
        """Extract element content from raw XML preserving format"""
        try:
            unit_pattern = rf'<(?:trans-unit|unit)[^>]*id=["\']{re.escape(unit_id)}["\'][^>]*>([\s\S]*?)</(?:trans-unit|unit)>'
            
            unit_match = re.search(unit_pattern, xml_content, re.IGNORECASE)
            if not unit_match:
                return ""
            
            unit_content = unit_match.group(1)

            element_pattern = rf'(<{element_name}[^>]*>)([\s\S]*?)</{element_name}>'

            element_match = re.search(element_pattern, unit_content, re.IGNORECASE)
            if not element_match:
                return ""

            # xml:space="preserve" makes leading/trailing whitespace content.
            content = element_match.group(2)
            if not XML_SPACE_PRESERVE.search(element_match.group(1)):
                content = content.strip()

            return html.unescape(content)
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
        wanted: dict[str, str] = {}
        for translation in translations:
            new_text = translation.get('aiResult') or translation.get('mtResult')
            if not new_text:
                continue
            unit_id = translation.get('unitId') or str(translation['segNumber'])
            wanted[unit_id] = new_text

        replacements_count = 0

        def rewrite(match: "re.Match[str]") -> str:
            nonlocal replacements_count
            unit_start, unit_content, unit_end = match.groups()
            unit_id = _unit_id(unit_start)
            if unit_id is None or unit_id not in wanted:
                return match.group(0)

            new_unit_content, changed = _fill_target(
                unit_content, _render_fragment(wanted[unit_id])
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
        original_units = _units_by_id(original)
        filled_units = _units_by_id(filled)
        issues: list[dict] = []

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

        for unit_id in original_units:
            if unit_id not in filled_units:
                issues.append(
                    {"unit_id": unit_id, "kind": "ids", "detail": "unit missing from filled file"}
                )
        for unit_id in filled_units:
            if unit_id not in original_units:
                issues.append(
                    {"unit_id": unit_id, "kind": "ids", "detail": "unit not present in original"}
                )

        changed: list[str] = []
        for unit_id, (before, after) in (
            (uid, (original_units[uid], filled_units[uid]))
            for uid in original_units
            if uid in filled_units
        ):
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
    match = re.search(r"""\bid\s*=\s*["']([^"']+)["']""", unit_start_tag)
    return match.group(1) if match else None


def _with_translated_state(open_tag: str) -> str:
    """Set state="translated" on a <target> opening tag, keeping other attributes."""
    if re.search(r"\bstate\s*=", open_tag):
        open_tag = re.sub(
            r"""(\bstate\s*=\s*)(["'])[^"']*\2""", r'\1"translated"', open_tag, count=1
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
    match = TARGET_ELEMENT.search(unit_content)
    if match:
        element = match.group(0)
        if element.endswith("/>"):
            open_tag = _with_translated_state(element[:-2] + ">")
        else:
            open_tag = _with_translated_state(element[: element.index(">") + 1])
        new_element = open_tag + rendered + "</target>"
        return (
            unit_content[: match.start()] + new_element + unit_content[match.end() :],
            True,
        )

    # No target yet: place it after seg-source when present, else after source.
    anchor = re.search(r"</seg-source>", unit_content, re.IGNORECASE) or re.search(
        r"</source>", unit_content, re.IGNORECASE
    )
    if anchor is None:
        return unit_content, False

    new_target = _with_translated_state("<target>") + rendered + "</target>"
    position = anchor.end()
    return unit_content[:position] + new_target + unit_content[position:], True


def _render_fragment(text: str) -> str:
    """Escape text runs while keeping well-formed XLIFF inline tags.

    Anything that is not a balanced, allowed inline tag is treated as plain
    text, so a model output containing '&' or a stray '<' can never produce a
    document that does not parse.
    """
    tags = list(INLINE_TAG.finditer(text))
    if text.count("<") != len(tags):
        return escape(text)

    stack: list[str] = []
    for tag in tags:
        closing, name, _, self_closing = tag.groups()
        if name.split(":")[-1] not in INLINE_ELEMENTS:
            return escape(text)
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
    for tag in tags:
        parts.append(escape(text[position : tag.start()]))
        parts.append(tag.group(0))
        position = tag.end()
    parts.append(escape(text[position:]))
    return "".join(parts)


SOURCE_ELEMENT = re.compile(r"<source\b[^>]*>[\s\S]*?</source>", re.IGNORECASE)


def _units_by_id(xml: str) -> dict[str, dict]:
    """unit id -> {start_tag, content, source}. Duplicate ids: last wins."""
    units: dict[str, dict] = {}
    for match in UNIT_ELEMENT.finditer(xml):
        unit_id = _unit_id(match.group(1))
        if unit_id is None:
            continue
        source = SOURCE_ELEMENT.search(match.group(2))
        units[unit_id] = {
            "start_tag": match.group(1),
            "content": match.group(2),
            "source": source.group(0) if source else "",
        }
    return units


def _target_parts(unit_content: str) -> dict | None:
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
    match = re.search(r"""\bstate\s*=\s*["']([^"']*)["']""", tag)
    return match.group(1) if match else None


def _tag_skeleton(fragment: str) -> list[str]:
    """'localname:id' for each opening or self-closing inline tag, in order."""
    skeleton: list[str] = []
    for closing, name, attrs, _ in INLINE_TAG.findall(fragment):
        local = name.split(":")[-1]
        if closing or local not in INLINE_ELEMENTS:
            continue
        id_match = re.search(r"""\bid\s*=\s*["']([^"']*)["']""", attrs)
        skeleton.append(f"{local}:{id_match.group(1) if id_match else ''}")
    return skeleton
