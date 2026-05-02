# src/infrastructure/runtime/weasyprint_patch.py
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
Runtime-Patch für WeasyPrint PDF/UA Tag-Mapping (Semantic Adapter Layer).
Ersetzt Monkeypatching durch eine robuste Plugin-Registry.
Fügt MathML, IDs und Role-Fallbacks dynamisch auf Node-Ebene hinzu,
ohne die Core-Tree-Builder-Logik von WeasyPrint zu zerstören.
"""

import logging
from typing import Any, Callable, Dict, List

import pydyf
import weasyprint.pdf.tags as wp_tags
from weasyprint.layout.absolute import AbsolutePlaceholder

logger = logging.getLogger("pdf-converter")

# ---------- Registries ----------

TAG_REGISTRY: Dict[str, str] = {}
RULE_REGISTRY: Dict[str, List[Callable]] = {}

_original_get_pdf_tag = wp_tags._get_pdf_tag
_original_build_tree = wp_tags._build_box_tree


# ---------- API ----------


def register_tag(html_tag: str, pdf_tag: str) -> None:
    """Registriert ein neues HTML-to-PDF Tag Mapping."""
    TAG_REGISTRY[html_tag.lower()] = pdf_tag


def register_rule(pdf_tag: str, rule_fn: Callable) -> None:
    """Registriert eine Business-Rule (Attribute Injection) für einen PDF-Tag."""
    RULE_REGISTRY.setdefault(pdf_tag, []).append(rule_fn)


# ---------- Patched Mapping ----------


def patched_get_pdf_tag(tag: str) -> str:
    """Löst Tags über die Registry auf (Fail-Fast)."""
    if not tag:
        return "NonStruct"
    tag_lower = tag.lower()
    if tag_lower in TAG_REGISTRY:
        return TAG_REGISTRY[tag_lower]
    return _original_get_pdf_tag(tag)


# ---------- Patched Tree Builder ----------


def patched_build_box_tree(
    box: Any,
    parent: Any,
    pdf: Any,
    page_number: int,
    nums: dict,
    links: list,
    tags: dict,
):
    """
    Fängt den generierten StructElem-Knoten ab und führt alle registrierten
    Regeln aus, um PDF/UA-Attribute (ActualText, Alt, ID) zu injizieren.
    """
    for element in _original_build_tree(
        box, parent, pdf, page_number, nums, links, tags
    ):
        struct_type = element.get("S")
        if not struct_type:
            yield element
            continue

        # Das führende '/' entfernen
        pdf_tag = str(struct_type)[1:]

        actual_box = box._box if isinstance(box, AbsolutePlaceholder) else box

        if pdf_tag in RULE_REGISTRY:
            for rule in RULE_REGISTRY[pdf_tag]:
                try:
                    rule(element, actual_box, pdf)
                except Exception as e:
                    logger.debug("Fehler in Regel für %s: %s", pdf_tag, e)

        yield element


# ---------- Accessibility Rules ----------


def formula_rule(element: Any, box: Any, pdf: Any) -> None:
    """PDF/UA Regel 7.7: Formeln benötigen ActualText oder Alt."""
    if box.element is None:
        return

    # Level 1: Visuelle Formel (Alt-Text)
    if "Alt" not in element:
        alt_text = box.element.attrib.get("aria-label") or box.element.text or "Formel"
        element["Alt"] = pydyf.String(alt_text)

    # Level 2 & 3: Sprechbare & Strukturierte Formel (MathML in ActualText)
    if "ActualText" not in element:
        mathml = box.element.attrib.get("data-mathml")
        if mathml:
            element["ActualText"] = pydyf.String(mathml)
        elif box.element.text:
            element["ActualText"] = pydyf.String(box.element.text)


def note_rule(element: Any, box: Any, pdf: Any) -> None:
    """PDF/UA Regel 7.9: Fußnoten benötigen zwingend eine ID."""
    if "ID" not in element:
        element["ID"] = pydyf.String(f"note_{id(box)}")


def figure_rule(element: Any, box: Any, pdf: Any) -> None:
    """WCAG Vorgabe: Bilder benötigen Alt-Text."""
    if box.element is None:
        return
    if "Alt" not in element:
        alt = box.element.attrib.get("alt") or "Abbildung"
        element["Alt"] = pydyf.String(alt)


def form_rule(element: Any, box: Any, pdf: Any) -> None:
    """PDF/UA Regel 7.18.4: Formulare ohne Widget brauchen Print/tv Role-Fallback."""
    if box.element is None:
        return
    if "Alt" not in element:
        alt = box.element.attrib.get("aria-label") or "Formularfeld"
        element["Alt"] = pydyf.String(alt)
    if "A" not in element:
        element["A"] = pydyf.Dictionary({"O": "/Print", "Role": "/tv"})


# ---------- Lifecycle ----------


def register_accessibility_rules() -> None:
    """Initiiert die Semantic Adapter Layer Registry."""
    register_tag("pac-formula", "Formula")
    register_tag("math", "Formula")
    register_tag("pac-note", "Note")
    register_tag("pac-figure", "Figure")
    register_tag("pac-form", "Form")
    register_tag("pac-caption", "Caption")

    register_rule("Formula", formula_rule)
    register_rule("Note", note_rule)
    register_rule("Figure", figure_rule)
    register_rule("Form", form_rule)


def apply_patch() -> None:
    """Aktiviert die Patches global vor der PDF Erzeugung."""
    register_accessibility_rules()
    wp_tags._get_pdf_tag = patched_get_pdf_tag
    wp_tags._build_box_tree = patched_build_box_tree
    logger.debug("🔧 WeasyPrint JIT-Patch (Semantic Adapter Layer) aktiviert.")
