"""Extract MCID-to-text signals from tagged PDF files.

This module is intentionally signal-only. It must not repair text, replace
document content, or modify the visual or semantic layer of the PDF.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import pikepdf

from src.infrastructure.pdf.tag_extractor import extract_existing_tags

HEADING_TAGS = {
    "h",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "heading",
}

TEXT_SHOW_OPERATORS = {"Tj", "TJ", "'", '"'}

HEX_TOKEN_PATTERN = re.compile(r"<([0-9A-Fa-f]+)>")
BFCHAR_PATTERN = re.compile(r"^<([0-9A-Fa-f]+)>\s+<([0-9A-Fa-f]+)>$")
BFRANGE_STRING_PATTERN = re.compile(
    r"^<([0-9A-Fa-f]+)>\s+<([0-9A-Fa-f]+)>\s+<([0-9A-Fa-f]+)>$",
)
BFRANGE_ARRAY_PATTERN = re.compile(
    r"^<([0-9A-Fa-f]+)>\s+"
    r"<([0-9A-Fa-f]+)>\s+"
    r"\x5b(.*)\x5d$",
)


def _write_result(
    result: dict[str, Any], output_path: str | Path | None
) -> None:
    """Write a result dictionary as JSON when an output path is provided."""
    if output_path is None:
        return

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_page_count(pdf_path: Path) -> int | None:
    """Read the number of pages without turning failures into hard errors."""
    try:
        with pikepdf.Pdf.open(pdf_path) as pdf:
            return len(pdf.pages)
    except Exception:  # noqa: BLE001
        return None


def _base_summary(page_count: int | None) -> dict[str, Any]:
    """Build the stable summary shape used by all result states."""
    return {
        "page_count": page_count,
        "font_count": 0,
        "to_unicode_font_count": 0,
        "mcid_ref_count": 0,
        "heading_mcid_ref_count": 0,
        "mcid_text_count": 0,
        "heading_mcid_text_count": 0,
        "unknown_code_count": 0,
    }


def _skipped_result(
    pdf_path: Path,
    reason: str,
    page_count: int | None = None,
) -> dict[str, Any]:
    """Build a stable skipped result."""
    return {
        "status": "skipped",
        "reason": reason,
        "source_pdf": str(pdf_path),
        "summary": _base_summary(page_count),
        "records": [],
    }


def _error_result(
    pdf_path: Path,
    error: str,
    page_count: int | None = None,
) -> dict[str, Any]:
    """Build a stable error result."""
    return {
        "status": "error",
        "reason": error,
        "source_pdf": str(pdf_path),
        "summary": _base_summary(page_count),
        "records": [],
    }


def _normalize_tag(value: Any) -> str:
    """Normalize PDF structure tag names for robust comparisons."""
    return str(value or "").strip().strip("/").lower()


def _coerce_int(value: Any) -> int | None:
    """Convert a PDF scalar value to int when possible."""
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _struct_tag(node: dict[str, Any]) -> str | None:
    """Return the preferred structure tag for path construction."""
    tag = node.get("standard_tag") or node.get("tag")
    if tag is None:
        return None

    text = str(tag).strip().strip("/")
    return text or None


def _has_heading_ancestor(struct_path: list[str]) -> bool:
    """Return whether a structure path contains a heading-like ancestor."""
    return any(_normalize_tag(tag) in HEADING_TAGS for tag in struct_path)


def _build_mcid_record(
    node: dict[str, Any],
    struct_path: list[str],
    inherited_page: int | None,
) -> dict[str, Any] | None:
    """Build one MCID reference record from a struct-tree leaf."""
    mcid = _coerce_int(node.get("mcid"))
    if mcid is None:
        return None

    page = _coerce_int(node.get("page"))
    if page is None:
        page = inherited_page

    nearest_tag = struct_path[-1] if struct_path else None

    return {
        "page": page,
        "mcid": mcid,
        "content_tag": nearest_tag,
        "struct_path": list(struct_path),
        "nearest_tag": nearest_tag,
        "has_heading_ancestor": _has_heading_ancestor(struct_path),
        "decoded_text": "",
        "fonts": [],
        "unknown_codes": [],
        "confidence": "struct_tree_only",
        "source": "struct_tree",
    }


def _walk_existing_tag_node(
    node: Any,
    struct_path: list[str],
    inherited_page: int | None,
    records: list[dict[str, Any]],
) -> None:
    """Collect MCID references from an existing_tags tree node."""
    if isinstance(node, list):
        for item in node:
            _walk_existing_tag_node(
                item,
                struct_path,
                inherited_page,
                records,
            )
        return

    if not isinstance(node, dict):
        return

    kind = node.get("kind")

    if kind == "struct":
        tag = _struct_tag(node)
        next_path = list(struct_path)
        if tag:
            next_path.append(tag)

        page = _coerce_int(node.get("page"))
        if page is None:
            page = inherited_page

        _walk_existing_tag_node(
            node.get("children", []),
            next_path,
            page,
            records,
        )
        return

    if kind in {"mcid", "mcr"}:
        record = _build_mcid_record(node, struct_path, inherited_page)
        if record is not None:
            records.append(record)
        return

    _walk_existing_tag_node(
        node.get("children", []),
        struct_path,
        inherited_page,
        records,
    )


def _collect_struct_mcid_records(
    existing_tags: dict[str, Any],
) -> list[dict[str, Any]]:
    """Collect MCID references with full structure paths."""
    tree = existing_tags.get("tree")
    if not isinstance(tree, dict):
        return []

    records: list[dict[str, Any]] = []
    _walk_existing_tag_node(
        tree.get("children", []),
        struct_path=[],
        inherited_page=None,
        records=records,
    )
    return records


def _decode_utf16be_hex(hex_value: str) -> str | None:
    """Decode a ToUnicode destination hex string."""
    if len(hex_value) % 2:
        return None

    try:
        raw = bytes.fromhex(hex_value)
    except ValueError:
        return None

    if not raw:
        return ""

    try:
        return raw.decode("utf-16-be")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


def _increment_hex_code(hex_value: str, offset: int) -> str:
    """Increment a fixed-width hexadecimal code."""
    width = len(hex_value)
    value = int(hex_value, 16) + offset
    return f"{value:0{width}x}"[-width:]


def _parse_bfchar_line(
    line: str,
    mapping: dict[bytes, str],
) -> None:
    """Parse one beginbfchar mapping line."""
    match = BFCHAR_PATTERN.match(line)
    if not match:
        return

    source_hex, destination_hex = match.groups()
    decoded = _decode_utf16be_hex(destination_hex)
    if decoded is None:
        return

    try:
        mapping[bytes.fromhex(source_hex)] = decoded
    except ValueError:
        return


def _parse_bfrange_line(
    line: str,
    mapping: dict[bytes, str],
) -> None:
    """Parse one beginbfrange mapping line."""
    array_match = BFRANGE_ARRAY_PATTERN.match(line)
    if array_match:
        start_hex, _end_hex, array_body = array_match.groups()
        destination_tokens = HEX_TOKEN_PATTERN.findall(array_body)
        start_value = int(start_hex, 16)

        for offset, destination_hex in enumerate(destination_tokens):
            decoded = _decode_utf16be_hex(destination_hex)
            if decoded is None:
                continue
            source_hex = _increment_hex_code(
                start_hex,
                start_value + offset - start_value,
            )
            try:
                mapping[bytes.fromhex(source_hex)] = decoded
            except ValueError:
                continue
        return

    string_match = BFRANGE_STRING_PATTERN.match(line)
    if not string_match:
        return

    start_hex, end_hex, destination_hex = string_match.groups()
    start_value = int(start_hex, 16)
    end_value = int(end_hex, 16)

    for source_value in range(start_value, end_value + 1):
        offset = source_value - start_value
        source_hex = f"{source_value:0{len(start_hex)}x}"
        target_hex = _increment_hex_code(destination_hex, offset)
        decoded = _decode_utf16be_hex(target_hex)
        if decoded is None:
            continue

        try:
            mapping[bytes.fromhex(source_hex)] = decoded
        except ValueError:
            continue


def _parse_to_unicode_cmap(cmap_bytes: bytes) -> dict[bytes, str]:
    """Parse a minimal subset of ToUnicode CMap mappings."""
    text = cmap_bytes.decode("latin-1", errors="replace")
    mapping: dict[bytes, str] = {}
    mode: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("%"):
            continue

        if "beginbfchar" in line:
            mode = "bfchar"
            continue
        if "endbfchar" in line:
            mode = None
            continue
        if "beginbfrange" in line:
            mode = "bfrange"
            continue
        if "endbfrange" in line:
            mode = None
            continue

        if mode == "bfchar":
            _parse_bfchar_line(line, mapping)
        elif mode == "bfrange":
            _parse_bfrange_line(line, mapping)

    return mapping


def _font_resource_dict(page: pikepdf.Page) -> pikepdf.Dictionary:
    """Return the page font resource dictionary if present."""
    resources = page.get("/Resources", {})
    if not isinstance(resources, pikepdf.Dictionary):
        return pikepdf.Dictionary()

    fonts = resources.get("/Font", {})
    if isinstance(fonts, pikepdf.Dictionary):
        return fonts

    return pikepdf.Dictionary()


def _font_label(font: Any) -> str | None:
    """Return a stable human-readable font label."""
    if not isinstance(font, pikepdf.Dictionary):
        return None

    base_font = font.get("/BaseFont")
    if base_font is not None:
        return str(base_font)

    subtype = font.get("/Subtype")
    if subtype is not None:
        return str(subtype)

    return None


def _build_font_decoders(
    page: pikepdf.Page,
) -> tuple[dict[str, dict[bytes, str]], dict[str, str], int, int]:
    """Build ToUnicode decoders for all page fonts."""
    fonts = _font_resource_dict(page)
    decoders: dict[str, dict[bytes, str]] = {}
    labels: dict[str, str] = {}

    for name, font in fonts.items():
        font_name = str(name)
        label = _font_label(font)
        labels[font_name] = label or font_name

        if not isinstance(font, pikepdf.Dictionary):
            continue
        if "/ToUnicode" not in font:
            continue

        try:
            cmap_bytes = bytes(font["/ToUnicode"].read_bytes())
        except Exception:  # noqa: BLE001
            continue

        mapping = _parse_to_unicode_cmap(cmap_bytes)
        if mapping:
            decoders[font_name] = mapping

    return decoders, labels, len(fonts), len(decoders)


def _decode_pdf_string(
    value: pikepdf.String,
    decoder: dict[bytes, str] | None,
) -> tuple[str, list[str], bool]:
    """Decode one PDF string object through a ToUnicode mapping."""
    raw = bytes(value)
    if decoder is None:
        return "", [raw.hex()], True

    if not raw:
        return "", [], False

    max_code_len = max((len(code) for code in decoder), default=1)
    position = 0
    parts: list[str] = []
    unknown_codes: list[str] = []

    while position < len(raw):
        decoded = None
        matched_len = 0
        remaining = len(raw) - position
        candidate_len = min(max_code_len, remaining)

        while candidate_len > 0:
            candidate = raw[position : position + candidate_len]
            if candidate in decoder:
                decoded = decoder[candidate]
                matched_len = candidate_len
                break
            candidate_len -= 1

        if decoded is None:
            unknown = raw[position : position + 1]
            unknown_codes.append(unknown.hex())
            position += 1
            continue

        parts.append(decoded)
        position += matched_len

    return "".join(parts), unknown_codes, False


def _active_mcid(marked_stack: list[dict[str, Any]]) -> int | None:
    """Return the innermost active MCID from the marked-content stack."""
    for item in reversed(marked_stack):
        mcid = item.get("mcid")
        if mcid is not None:
            return mcid
    return None


def _extract_mcid_from_bdc_operands(operands: Any) -> int | None:
    """Extract /MCID from BDC operands if available."""
    if len(operands) < 2:
        return None

    properties = operands[1]
    if not isinstance(properties, pikepdf.Dictionary):
        return None
    if "/MCID" not in properties:
        return None

    return _coerce_int(properties.get("/MCID"))


def _append_text_signal(
    signal: dict[str, Any],
    text: str,
    font_name: str | None,
    font_labels: dict[str, str],
    unknown_codes: list[str],
    undecoded: bool,
) -> None:
    """Append decoded or undecoded text information to one content signal."""
    if text:
        signal["text_parts"].append(text)

    if font_name:
        signal["fonts"].add(font_name)
        label = font_labels.get(font_name)
        if label:
            signal["font_labels"].add(label)

    signal["unknown_codes"].extend(unknown_codes)
    if undecoded:
        signal["undecoded"] = True


def _iter_text_strings(operator: str, operands: Any) -> list[pikepdf.String]:
    """Extract PDF string operands from text-showing operators."""
    if operator == "Tj":
        if operands and isinstance(operands[0], pikepdf.String):
            return [operands[0]]
        return []

    if operator == "TJ":
        if not operands or not isinstance(operands[0], pikepdf.Array):
            return []
        return [
            item for item in operands[0] if isinstance(item, pikepdf.String)
        ]

    if operator == "'":
        if operands and isinstance(operands[0], pikepdf.String):
            return [operands[0]]
        return []

    if operator == '"':
        if operands and isinstance(operands[-1], pikepdf.String):
            return [operands[-1]]
        return []

    return []


def _collect_content_stream_text(
    pdf_path: Path,
) -> tuple[dict[tuple[int, int], dict[str, Any]], dict[str, int]]:
    """Collect decoded text snippets grouped by page and MCID."""
    content_signals: dict[tuple[int, int], dict[str, Any]] = {}
    font_count = 0
    to_unicode_font_count = 0

    with pikepdf.Pdf.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            decoders, font_labels, page_font_count, page_to_unicode_count = (
                _build_font_decoders(page)
            )
            font_count += page_font_count
            to_unicode_font_count += page_to_unicode_count

            current_font: str | None = None
            marked_stack: list[dict[str, Any]] = []

            for operands, operator in pikepdf.parse_content_stream(page):
                op = str(operator)

                if op == "BDC":
                    marked_stack.append(
                        {
                            "mcid": _extract_mcid_from_bdc_operands(operands),
                        },
                    )
                    continue

                if op == "BMC":
                    marked_stack.append({"mcid": None})
                    continue

                if op == "EMC":
                    if marked_stack:
                        marked_stack.pop()
                    continue

                if op == "Tf" and operands:
                    current_font = str(operands[0])
                    continue

                if op not in TEXT_SHOW_OPERATORS:
                    continue

                mcid = _active_mcid(marked_stack)
                if mcid is None:
                    continue

                key = (page_index, mcid)
                signal = content_signals.setdefault(
                    key,
                    {
                        "text_parts": [],
                        "fonts": set(),
                        "font_labels": set(),
                        "unknown_codes": [],
                        "undecoded": False,
                    },
                )

                decoder = decoders.get(current_font or "")
                for text_string in _iter_text_strings(op, operands):
                    text, unknown_codes, undecoded = _decode_pdf_string(
                        text_string,
                        decoder,
                    )
                    _append_text_signal(
                        signal,
                        text,
                        current_font,
                        font_labels,
                        unknown_codes,
                        undecoded,
                    )

    stats = {
        "font_count": font_count,
        "to_unicode_font_count": to_unicode_font_count,
    }
    return content_signals, stats


def _confidence_for_content_signal(
    decoded_text: str,
    unknown_codes: list[str],
    undecoded: bool,
) -> str:
    """Derive a conservative confidence label for a content signal."""
    if decoded_text and not unknown_codes and not undecoded:
        return "content_stream_to_unicode"
    if decoded_text:
        return "partial_content_stream_to_unicode"
    if unknown_codes or undecoded:
        return "undecoded_content_stream"
    return "struct_tree_only"


def _merge_content_signals(
    records: list[dict[str, Any]],
    content_signals: dict[tuple[int, int], dict[str, Any]],
) -> None:
    """Merge content-stream text signals into StructTree MCID records."""
    for record in records:
        page = _coerce_int(record.get("page"))
        mcid = _coerce_int(record.get("mcid"))
        if page is None or mcid is None:
            continue

        signal = content_signals.get((page, mcid))
        if signal is None:
            continue

        decoded_text = "".join(signal["text_parts"])
        unknown_codes = list(signal["unknown_codes"])
        undecoded = bool(signal["undecoded"])

        record["decoded_text"] = decoded_text
        record["fonts"] = sorted(signal["fonts"])
        record["font_labels"] = sorted(signal["font_labels"])
        record["unknown_codes"] = unknown_codes
        record["confidence"] = _confidence_for_content_signal(
            decoded_text,
            unknown_codes,
            undecoded,
        )
        record["source"] = "pikepdf_content_stream"


def _success_result(
    pdf_path: Path,
    page_count: int | None,
    records: list[dict[str, Any]],
    content_stats: dict[str, int],
) -> dict[str, Any]:
    """Build a success result for currently available MCID signals."""
    summary = _base_summary(page_count)
    summary["font_count"] = content_stats.get("font_count", 0)
    summary["to_unicode_font_count"] = content_stats.get(
        "to_unicode_font_count",
        0,
    )
    summary["mcid_ref_count"] = len(records)
    summary["heading_mcid_ref_count"] = sum(
        1 for record in records if record["has_heading_ancestor"]
    )
    summary["mcid_text_count"] = sum(
        1 for record in records if record.get("decoded_text")
    )
    summary["heading_mcid_text_count"] = sum(
        1
        for record in records
        if record.get("decoded_text") and record["has_heading_ancestor"]
    )
    summary["unknown_code_count"] = sum(
        len(record.get("unknown_codes", [])) for record in records
    )

    return {
        "status": "success",
        "source_pdf": str(pdf_path),
        "summary": summary,
        "records": records,
    }


def extract_mcid_text_signals(
    pdf_path: str | Path,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Extract MCID-to-text signals from a PDF.

    The implementation collects StructTree MCID references with full structure
    paths and enriches them with conservative content-stream text decoded
    through each active font's ``/ToUnicode`` CMap where possible.

    Args:
        pdf_path: Path to the source PDF.
        output_path: Optional path for the JSON signal artifact.

    Returns:
        A JSON-serializable result dictionary.
    """
    source = Path(pdf_path)
    page_count = _read_page_count(source)

    try:
        existing_tags = extract_existing_tags(source)
        status = existing_tags.get("status")

        if status == "skipped":
            result = _skipped_result(
                source,
                str(existing_tags.get("reason", "StructTreeRoot missing")),
                page_count,
            )
            _write_result(result, output_path)
            return result

        if status != "success":
            result = _error_result(
                source,
                str(existing_tags.get("reason", "tag extraction failed")),
                page_count,
            )
            _write_result(result, output_path)
            return result

        records = _collect_struct_mcid_records(existing_tags)
        content_signals, content_stats = _collect_content_stream_text(source)
        _merge_content_signals(records, content_signals)

        result = _success_result(source, page_count, records, content_stats)
        _write_result(result, output_path)
        return result

    except Exception as exc:  # noqa: BLE001
        result = _error_result(source, str(exc), page_count)
        _write_result(result, output_path)
        return result


def _build_parser() -> argparse.ArgumentParser:
    """Build the command line parser."""
    parser = argparse.ArgumentParser(
        description="Extract MCID-to-text signals from a tagged PDF.",
    )
    parser.add_argument("pdf_path", help="Input PDF path.")
    parser.add_argument(
        "--output",
        "-o",
        help="Optional JSON output path.",
        default=None,
    )
    return parser


def main() -> int:
    """Run the command line interface."""
    parser = _build_parser()
    args = parser.parse_args()

    result = extract_mcid_text_signals(args.pdf_path, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0 if result["status"] != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
