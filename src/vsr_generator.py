# src/vsr_generator.py
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Visual Screenreader (VSR) Core Engine.
Liest den logischen Tag-Baum (StructTreeRoot) eines PDFs und generiert
eine interaktive, PAC 2026-äquivalente HTML-Repräsentation.

ARCHITEKTUR FIX & BUG REPAIR:
1. Pill-Spacing: Exakte Leerzeichen-Platzierung nach Pills und Text.
2. Empty Block Preservation: Leere Blöcke bleiben im DOM sichtbar.
3. Inline-Tag Spacing: Keine Newlines, nur Leerzeichen als Separator.
4. Text Extraction: Span-level (nicht Zeilen-level) für MCID-Sync.
5. RoleMap Context: Resolver sucht im StructTreeRoot, nicht im Root.
"""

import html
import logging
from pathlib import Path
from typing import Any, Dict, List, Set

import fitz  # PyMuPDF
import pikepdf

logger = logging.getLogger("pdf-converter")

VSR_CSS = (
    "body { font-family: 'Segoe UI', Tahoma, Verdana, sans-serif; "
    "background-color: #EFEFEF; padding: 20px; }\n"
    ".block { display: flex; flex-direction: row; border: 1px solid "
    "#1E2D32; margin: 2px; border-radius: 2px; overflow: hidden; }\n"
    ".tag-label { writing-mode: vertical-rl; transform: rotate(180deg); "
    "text-align: center; padding: 6px 4px; font-weight: bold; "
    "color: white; font-size: 11px; display: flex; align-items: center; "
    "justify-content: center; min-width: 18px; "
    "border-right: 1px solid rgba(0,0,0,0.2); }\n"
    ".block-children { flex-grow: 1; padding: 4px 6px; display: block; "
    "line-height: 1.5; color: #222; font-size: 14px; }\n"
    ".bg-document, .bg-div, .bg-part, .bg-art, .bg-sect "
    "{ background-color: #37535C; }\n"
    ".lbl-document, .lbl-div, .lbl-part, .lbl-art, .lbl-sect "
    "{ background-color: #2B424A; }\n"
    ".bg-h { background-color: #F8CECC; } "
    ".lbl-h { background-color: #CC0000; }\n"
    ".bg-p { background-color: #E2E8C9; } "
    ".lbl-p { background-color: #799920; }\n"
    ".bg-table, .bg-tr, .bg-th, .bg-td, .bg-thead, .bg-tbody, .bg-tfoot "
    "{ background-color: #E0DAF5; }\n"
    ".lbl-table, .lbl-tr, .lbl-th, .lbl-td, .lbl-thead, .lbl-tbody, "
    ".lbl-tfoot { background-color: #674EA7; }\n"
    ".bg-l, .bg-li, .bg-lbody, .bg-lbl { background-color: #D3E4F4; } "
    ".lbl-l, .lbl-li, .lbl-lbody, .lbl-lbl { background-color: #2B78E4; "
    "}\n"
    ".bg-note { background-color: #FCE5CD; } "
    ".lbl-note { background-color: #E69138; }\n"
    ".bg-figure, .bg-caption { background-color: #FFF2CC; } "
    ".lbl-figure, .lbl-caption { background-color: #D6B656; }\n"
    ".bg-form { background-color: #DAE8FC; } "
    ".lbl-form { background-color: #6C8EBF; }\n"
    ".bg-formula, .bg-math { background-color: #E1D5E7; } "
    ".lbl-formula, .lbl-math { background-color: #9673A6; }\n"
    ".pac-span-start, .pac-span-end { background-color: #37535C; "
    "color: #fff; padding: 2px 6px; border-radius: 12px; font-size: 11px; "
    "font-weight: bold; margin: 0 3px; display: inline-block; "
    "vertical-align: baseline; }\n"
    ".pac-alt { background-color: #E69138; }\n"
    ".pac-act { background-color: #4CAF50; }\n"
    ".text-content { color: #222; font-size: 14px; display: inline; }\n"
)


class RoleMapResolver:
    """Isolierter Adapter zur Auflösung von benutzerdefinierten Tags."""

    def __init__(self, struct_tree_root: pikepdf.Dictionary):
        """Initialisiert RoleMap aus StructTreeRoot."""
        self.role_map: Dict[str, str] = {}
        if "/RoleMap" in struct_tree_root:
            role_map_dict = struct_tree_root.get("/RoleMap")
            if isinstance(role_map_dict, pikepdf.Dictionary):
                for key, val in role_map_dict.items():
                    k_str = str(key).strip("/")
                    v_str = str(val).strip("/")
                    self.role_map[k_str] = v_str

    def resolve(self, tag: str) -> str:
        """Löst das Standard-Tag auf, schützt vor Zyklen."""
        visited: Set[str] = set()
        curr = tag
        while curr in self.role_map and curr not in visited:
            visited.add(curr)
            curr = self.role_map[curr]
        return curr


class TextExtractionWorker:
    """Extrahiert Text auf Span-Level (nicht Zeilen-Level)."""

    @staticmethod
    def extract(pdf_path: Path) -> List[str]:
        """
        Extrahiert Text sequenziell pro Span-Element.
        Keine Zeilen-Gruppierung, um 1:1 MCID-Sync zu garantieren.
        """
        spans: List[str] = []
        try:
            with fitz.open(pdf_path) as doc:
                for page in doc:
                    blocks = page.get_text("dict", sort=False).get(
                        "blocks", []
                    )
                    for block in blocks:
                        if block.get("type") != 0:
                            continue
                        for line in block.get("lines", []):
                            for span in line.get("spans", []):
                                txt = span.get("text", "")
                                if txt:
                                    spans.append(txt)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.debug("Fehler bei VSR Text-Extraktion: %s", e)
        return spans


class StructTreeWalker:
    """Traversiert den logischen PDF-Baum mit Sensor-Fusion."""

    INLINE_TAGS = {"SPAN", "LINK", "QUOTE", "REF", "BIBENTRY"}

    def __init__(self, role_map: RoleMapResolver, text_queue: List[str]):
        """Initialisiert Walker mit RoleMap und Text-Queue."""
        self.role_map = role_map
        self.text_queue = text_queue

    @staticmethod
    def get_css_class(tag_upper: str) -> str:
        """Mappt logische Tags deterministisch auf PAC CSS-Klassen."""
        if tag_upper in ["DOCUMENT", "DIV", "PART", "ART", "SECT"]:
            return tag_upper.lower()
        if tag_upper.startswith("H") and len(tag_upper) == 2:
            if tag_upper[1].isdigit():
                return "h"
        if tag_upper == "P":
            return "p"
        if tag_upper in [
            "TABLE",
            "TR",
            "TH",
            "TD",
            "THEAD",
            "TBODY",
            "TFOOT",
        ]:
            return tag_upper.lower()
        if tag_upper in ["L", "LI", "LBL", "LBODY"]:
            return tag_upper.lower()
        if tag_upper in ["NOTE", "REFERENCE"]:
            return "note"
        if tag_upper in ["FIGURE", "CAPTION"]:
            return tag_upper.lower()
        if tag_upper == "FORM":
            return "form"
        if tag_upper in ["FORMULA", "MATH"]:
            return "formula"
        return tag_upper.lower()

    def _format_text(self, txt: str) -> str:
        """Kapselt Text für VSR mit nachgestelltem Leerzeichen."""
        txt = txt.strip()
        if not txt:
            return ""
        escaped = html.escape(txt)
        return f"<span class='text-content'>{escaped}</span> "

    def walk(self, node: Any) -> str:
        """Rekursive Traversierung des physikalischen DOMs zur VSR."""
        if isinstance(node, (list, tuple, pikepdf.Array)):
            return "".join(self.walk(kid) for kid in node)

        is_mcid = False
        if isinstance(node, int):
            is_mcid = True
        elif isinstance(node, pikepdf.Object):
            if not isinstance(
                node,
                (
                    pikepdf.Dictionary,
                    pikepdf.Array,
                    pikepdf.Name,
                    pikepdf.String,
                ),
            ):
                try:
                    int(node)
                    is_mcid = True
                except (TypeError, ValueError):
                    pass

        if is_mcid:
            txt = self.text_queue.pop(0) if self.text_queue else ""
            return self._format_text(txt)

        if not isinstance(node, pikepdf.Dictionary):
            return ""

        type_val = node.get("/Type")

        if type_val == "/MCR":
            txt = self.text_queue.pop(0) if self.text_queue else ""
            return self._format_text(txt)

        if type_val == "/OBJR":
            return "<span class='pac-span-start'>Objekt/Link</span> "

        if "/S" in node:
            raw_tag = str(node.get("/S", "UNKNOWN")).replace("/", "")
            tag = self.role_map.resolve(raw_tag)
            tag_upper = tag.upper()

            alt_text = ""
            if "/Alt" in node:
                alt_text = str(node.get("/Alt"))

            actual_text = ""
            if "/ActualText" in node:
                actual_text = str(node.get("/ActualText"))

            kids_html = ""
            if "/K" in node:
                # Figure-Elemente mit /Alt beschreiben ein Bild.
                # Deren MCID verweist typischerweise auf Bild-/XObject-Content,
                # nicht auf lesbaren Text. Wenn wir diese MCIDs über die globale
                # Text-Queue konsumieren, verschiebt sich die Zuordnung aller
                # nachfolgenden StructTree-Texte.
                if tag_upper == "FIGURE" and alt_text:
                    kids_html = ""
                else:
                    kids_html = self.walk(node.get("/K"))

            alt_html = ""
            if alt_text:
                esc_alt = html.escape(alt_text)
                alt_html = (
                    f"<span class='pac-span-start pac-alt'>Alt: "
                    f"{esc_alt}</span> "
                )

            act_html = ""
            if actual_text:
                esc_act = html.escape(actual_text)
                act_html = (
                    f"<span class='pac-span-start pac-act'>ActualText: "
                    f"{esc_act}</span> "
                )

            if tag_upper in self.INLINE_TAGS:
                start_pill = (
                    f"<span class='pac-span-start'>{tag.capitalize()}</span> "
                )
                end_pill = (
                    f"<span class='pac-span-end'>{tag.capitalize()}</span> "
                )
                return f"{start_pill}{act_html}{alt_html}{kids_html}{end_pill}"

            css_cls = self.get_css_class(tag_upper)
            html_out = f"<div class='block bg-{css_cls}'>\n"
            html_out += (
                f"<div class='tag-label lbl-{css_cls}'>{tag_upper}</div>\n"
            )
            html_out += "<div class='block-children'>\n"
            html_out += act_html
            html_out += alt_html
            html_out += kids_html
            html_out += "</div>\n</div>\n"

            return html_out

        return ""


def generate_physical_vsr(pdf_path: Path, output_path: Path) -> bool:
    """Haupt-Fassade zur VSR-Generierung."""
    if not pdf_path.exists():
        logger.error("VSR Fehler: Datei existiert nicht %s", pdf_path)
        return False

    try:
        text_queue = TextExtractionWorker.extract(pdf_path)

        with pikepdf.open(pdf_path) as pdf:
            root = pdf.Root
            if "/StructTreeRoot" not in root:
                logger.warning("Das PDF enthält keine Tags.")
                return False

            struct_tree = root.StructTreeRoot

            role_map = RoleMapResolver(struct_tree)
            walker = StructTreeWalker(role_map, text_queue)

            html_head = [
                "<!DOCTYPE html>",
                "<html>",
                "<head>",
                "<meta charset='utf-8'>",
                "<title>PAC 2026 Visual Screenreader</title>",
                f"<style>\n{VSR_CSS}</style>",
                "</head>",
                "<body>",
            ]

            body_html = ""
            if "/K" in struct_tree:
                body_html = walker.walk(struct_tree.get("/K"))

            html_tail = ["</body></html>"]

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(
                    "\n".join(html_head)
                    + "\n"
                    + body_html
                    + "\n"
                    + "\n".join(html_tail)
                )

            return True

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Kritischer Fehler bei VSR Generierung: %s", e)
        return False
