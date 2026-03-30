# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Sanitization & Validation Facade (Hybrid Mode).
Kombiniert KI-Labels mit dem Typografie-Experten (PyMuPDF),
um übersehene Überschriften fehlerfrei anhand echter Font-Metriken zu taggen.
"""

import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("pdf-converter")


class HeadingState:
    """Verwaltet den lückenlosen Hierarchie-Status über alle Seiten hinweg."""

    def __init__(self) -> None:
        self.current_h = 0
        self.h1_found = False


def remove_control_characters(md_text: str) -> str:
    """Sanitization Pattern: Entfernt unsichtbare ASCII-Kontrollzeichen."""
    text = unicodedata.normalize("NFC", md_text)
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)


def _extract_typography_data(pdf_path: Path) -> Dict[int, List[Dict]]:
    """Nutzt den PyMuPDF-Experten, um exakte Font-Metriken zu extrahieren."""
    page_fonts: Dict[int, List[Dict]] = {}
    try:
        import fitz  # pylint: disable=import-outside-toplevel

        with fitz.open(pdf_path) as doc:
            for i, page in enumerate(doc):
                p_num = i + 1
                page_fonts[p_num] = []
                for block in page.get_text("dict").get("blocks", []):
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            if span.get("text", "").strip():
                                page_fonts[p_num].append(
                                    {
                                        "bbox": span["bbox"],
                                        "size": span.get("size", 10.0),
                                        "is_bold": bool(span.get("flags", 0) & 16),
                                    }
                                )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.debug("Typografie-Scan übersprungen: %s", e)
    return page_fonts


def _flush_list(list_items: List[Dict], new_elements: List[Dict]) -> None:
    """Packt angesammelte Listen-Items in ein Listen-Tag."""
    if list_items:
        new_elements.append({"type": "list", "items": list_items.copy()})
        list_items.clear()


def _get_best_span(bbox: List[float], page_fonts: List[Dict]) -> Optional[Dict]:
    """Findet den passendsten (größten) Font-Span für eine Bounding Box."""
    intersecting = [
        s
        for s in page_fonts
        if not (
            bbox[2] < s["bbox"][0]
            or bbox[0] > s["bbox"][2]
            or bbox[3] < s["bbox"][1]
            or bbox[1] > s["bbox"][3]
        )
    ]
    return max(intersecting, key=lambda s: s["size"]) if intersecting else None


def _calculate_median_size(spatial_dom: Dict[str, Any], page_fonts: Dict) -> float:
    """Berechnet die Median-Schriftgröße des Dokuments."""
    all_sizes = [span["size"] for spans in page_fonts.values() for span in spans]
    if not all_sizes:
        for page in spatial_dom.get("pages", []):
            for el in page.get("elements", []):
                h = abs(
                    el.get("bbox", [0, 0, 0, 0])[3] - el.get("bbox", [0, 0, 0, 0])[1]
                )
                if h > 2.0:
                    all_sizes.append(h)
    if all_sizes:
        all_sizes.sort()
        return all_sizes[len(all_sizes) // 2]
    return 11.0


def _smooth_heading(raw_h: int, state: HeadingState) -> int:
    """Verhindert Sprünge in der Überschriften-Hierarchie (z.B. H1 -> H3)."""
    final_h = 1 if state.current_h == 0 else min(raw_h, state.current_h + 1)
    if final_h == 1:
        if state.h1_found:
            final_h = 2
        else:
            state.h1_found = True
    state.current_h = final_h
    return final_h


def _process_heading(
    el: Dict[str, Any],
    true_size: float,
    med: float,
    state: HeadingState,
    el_type: str,
    docling_head: bool,
) -> Dict[str, Any]:
    """Wandelt ein Element in eine validierte Überschrift um."""
    if true_size > med * 1.8:
        raw_h = 1
    elif true_size > med * 1.4:
        raw_h = 2
    elif true_size > med * 1.1:
        raw_h = 3
    else:
        raw_h = int(el_type[1]) if docling_head else 3

    el["type"] = f"h{_smooth_heading(raw_h, state)}"
    return el


def _process_page_elements(
    elements: List[Dict], page_fonts: List[Dict], med: float, state: HeadingState
) -> List[Dict]:
    """Isolierte Verarbeitungsschleife für die Elemente einer Seite."""
    new_els: List[Dict] = []
    list_items: List[Dict] = []

    for el in elements:
        el_t = el.get("type", "p")
        if el_t not in ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li"]:
            _flush_list(list_items, new_els)
            new_els.append(el)
            continue

        text = el.get("text", "").strip()
        if not text:
            continue

        bbox = el.get("bbox", [0, 0, 0, 0])
        true_size = abs(bbox[3] - bbox[1])
        is_bold = False

        best_span = _get_best_span(bbox, page_fonts)
        if best_span:
            true_size = best_span["size"]
            is_bold = best_span["is_bold"]

        is_form = text.startswith("$$") or text.startswith("\\")
        is_cont = "@" in text and "." in text
        mult = 1.15 if is_bold else 1.25
        docling_h = el_t.startswith("h") and not is_cont
        looks_h = (
            (true_size > med * mult)
            and (len(text.split()) < 15)
            and not is_form
            and not is_cont
        )

        if looks_h or docling_h:
            _flush_list(list_items, new_els)
            new_els.append(_process_heading(el, true_size, med, state, el_t, docling_h))
            continue

        is_mark = bool(re.match(r"^([-*•◦▪]|\d+\.|[a-zA-Z]\)|\[\d+\])\s+", text))
        if (el_t == "li" or is_mark) and true_size <= med * 1.3:
            el["type"] = "li"
            list_items.append(el)
            continue

        _flush_list(list_items, new_els)
        el["type"] = "p"
        new_els.append(el)

    _flush_list(list_items, new_els)
    return new_els


def repair_spatial_dom(
    spatial_dom: Dict[str, Any], pdf_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Facade Pattern: Initiiert die DOM-Reparatur."""
    logger.info("🤖 Typografie-Experte (PyMuPDF) prüft Font-Metriken...")

    p_fonts = (
        _extract_typography_data(pdf_path) if pdf_path and pdf_path.exists() else {}
    )
    med_size = _calculate_median_size(spatial_dom, p_fonts)
    state = HeadingState()

    for page in spatial_dom.get("pages", []):
        p_num = page.get("page_num")
        page["elements"] = _process_page_elements(
            page.get("elements", []), p_fonts.get(p_num, []), med_size, state
        )

    return spatial_dom


def enforce_pdfua_heading_hierarchy(md_text: str) -> str:
    """Fallback."""
    return md_text


def enforce_pdfua_list_structure(md_text: str) -> str:
    """Fallback."""
    return md_text


def repair_markdown_for_pdfua(md_text: str) -> str:
    """Fallback."""
    return remove_control_characters(md_text)
