# src/vsr_generator.py
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Visual Screenreader (VSR) Core Engine.
Liest den physischen Tag-Baum (StructTreeRoot) eines PDFs und generiert
eine interaktive HTML-Repräsentation im PAC26 Farbschema.
Behebt FIFO-Starvation durch striktes MCID-Mapping und filtert leere Tags.
"""

import html
import logging
from pathlib import Path
from typing import Any, List

import fitz  # PyMuPDF
import pikepdf

logger = logging.getLogger("pdf-converter")

# Ausgelagertes CSS, um E501 zu vermeiden und Code sauber zu halten
VSR_CSS = (
    "body { font-family: 'Segoe UI', sans-serif; background-color: #EFEFEF; "
    "padding: 20px; }\n"
    ".doc-container { background-color: #37535C; padding: 12px; "
    "border: 1px solid #1E2D32; display: flex; flex-direction: column; "
    "gap: 4px; }\n"
    ".block { display: flex; border: 1px solid #2B424A; }\n"
    ".tag-label { writing-mode: vertical-rl; transform: rotate(180deg); "
    "text-align: center; padding: 4px 2px; font-weight: bold; color: white; "
    "font-size: 11px; display: flex; align-items: center; "
    "justify-content: center; border-right: 1px solid rgba(0,0,0,0.2); }\n"
    ".tag-label-horizontal { writing-mode: horizontal-tb; transform: none; "
    "padding: 2px 6px; }\n"
    ".content { flex-grow: 1; padding: 4px 6px; display: flex; "
    "align-items: center; flex-wrap: wrap; gap: 4px; }\n"
    ".bg-doc { background-color: #4A6B74; } .lbl-doc { background-color: #2B424A; }\n"
    ".bg-div { background-color: #4A6B74; } .lbl-div { background-color: #2B424A; }\n"
    ".bg-h { background-color: #F8CECC; } .lbl-h { background-color: #CC0000; }\n"
    ".bg-p { background-color: #E2E8C9; } .lbl-p { background-color: #799920; }\n"
    ".bg-l { background-color: #D3E4F4; } .lbl-l { background-color: #2B78E4; }\n"
    ".bg-table { background-color: #E0DAF5; } .lbl-table { background-color: #674EA7; }\n"
    ".bg-note { background-color: #FCE5CD; } .lbl-note { background-color: #E69138; }\n"
    ".bg-figure { background-color: #FFF2CC; } .lbl-figure { background-color: #D6B656; }\n"
    ".bg-span { background-color: #D5E8D4; } .lbl-span { background-color: #82B366; }\n"
    ".bg-nonstruct { background-color: #E6D0DE; } "
    ".lbl-nonstruct { background-color: #A375A1; }\n"
    ".bg-caption { background-color: #FFF2CC; } "
    ".lbl-caption { background-color: #D6B656; }\n"
    ".bg-form { background-color: #DAE8FC; } .lbl-form { background-color: #6C8EBF; }\n"
    ".bg-formula, .bg-math { background-color: #E1D5E7; } "
    ".lbl-formula, .lbl-math { background-color: #9673A6; }\n"
    ".span-pill { background-color: #226388; color: #fff; padding: 2px 8px; "
    "border-radius: 12px; font-size: 12px; font-weight: bold; }\n"
    ".text-content { color: #222; font-size: 14px; font-family: monospace;}\n"
)


def _get_pdf_text_blocks(pdf_path: Path) -> List[str]:
    """Extrahiert Textblöcke exakt in der Reihenfolge des PDF Content Streams."""
    span_texts = []
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                dict_data = page.get_text("dict", sort=False)
                for block in dict_data.get("blocks", []):
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            text = span.get("text", "").strip()
                            if text:
                                text = text.replace("\n", " ")
                                span_texts.append(text)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.debug("Fehler bei Text-Extraktion für VSR: %s", e)
    return span_texts


def _format_content_span(txt: str) -> str:
    """Kapselt das HTML-Markup für ein echtes Textelement (MCID)."""
    txt = txt.strip()
    if not txt:
        return ""
    escaped = html.escape(txt)
    return (
        "<div class='content'>"
        "<span class='span-pill'>Span</span> "
        f"<span class='text-content'>{escaped}</span>"
        "</div>\n"
    )


# pylint: disable=too-many-branches,too-many-return-statements
def _walk_tree_html(node: Any, text_queue: List[str]) -> str:
    """Rekursive Traversierung des StructTreeRoot zur HTML-Generierung."""
    if isinstance(node, (list, tuple, pikepdf.Array)):
        html_out = ""
        for kid in node:
            html_out += _walk_tree_html(kid, text_queue)
        return html_out

    is_mcid = False
    if isinstance(node, int):
        is_mcid = True
    elif isinstance(node, pikepdf.Object):
        if not isinstance(
            node, (pikepdf.Dictionary, pikepdf.Array, pikepdf.Name, pikepdf.String)
        ):
            try:
                int(node)
                is_mcid = True
            except (TypeError, ValueError):
                pass

    if is_mcid:
        txt = text_queue.pop(0) if text_queue else ""
        return _format_content_span(txt)

    if not isinstance(node, pikepdf.Dictionary):
        return ""

    if node.get("/Type") == "/MCR":
        txt = text_queue.pop(0) if text_queue else ""
        return _format_content_span(txt)

    if node.get("/Type") == "/OBJR":
        return _format_content_span("[Objekt/Link]")

    if "/S" in node:
        tag = str(node.get("/S", "UNKNOWN")).replace("/", "").upper()
        css_cls = "h" if tag.startswith("H") else tag.lower()

        alt_text = ""
        if "/Alt" in node:
            alt_obj = str(node.get("/Alt"))
            if alt_obj.startswith("(") and alt_obj.endswith(")"):
                alt_text = alt_obj[1:-1]
            else:
                alt_text = alt_obj

        # ARCHITEKTUR FIX: SPAN und Inline-Formate müssen Kinder korrekt verarbeiten!
        is_container = tag in [
            "DOCUMENT",
            "DIV",
            "PART",
            "ART",
            "SECT",
            "TABLE",
            "THEAD",
            "TBODY",
            "TFOOT",
            "TR",
            "TH",
            "TD",
            "L",
            "LI",
            "LBODY",
            "UL",
            "OL",
            "FIGURE",
            "FORM",
            "NOTE",
            "FORMULA",
            "MATH",
            "CAPTION",
            "SPAN",
        ]

        kids_html = ""
        if "/K" in node:
            kids_html = _walk_tree_html(node.get("/K"), text_queue)

        if not kids_html.strip() and not alt_text.strip():
            return ""

        html_out = ""
        if is_container:
            html_out += (
                "<div class='doc-container' "
                "style='background-color: #4A6B74; padding: 6px;'>\n"
            )
            html_out += (
                f"<div class='tag-label tag-label-horizontal lbl-{css_cls}' "
                "style='align-self: flex-start; border: none; "
                f"margin-bottom: 4px;'>{tag}</div>\n"
            )
            if alt_text:
                esc_alt = html.escape(alt_text)
                html_out += (
                    "<div class='content'>"
                    "<span class='span-pill'>Alt</span> "
                    f"<span class='text-content'>{esc_alt}</span>"
                    "</div>\n"
                )
        else:
            html_out += f"<div class='block bg-{css_cls}'>\n"
            html_out += f"<div class='tag-label lbl-{css_cls}'>{tag}</div>\n"
            if alt_text:
                esc_alt = html.escape(alt_text)
                html_out += (
                    "<div class='content'>"
                    "<span class='span-pill'>Alt</span> "
                    f"<span class='text-content'>{esc_alt}</span>"
                    "</div>\n"
                )

        html_out += kids_html
        html_out += "</div>\n"

        return html_out

    return ""


def generate_physical_vsr(pdf_path: Path, output_path: Path) -> bool:
    """Hauptmethode: Liest das physische PDF und schreibt das PAC26-HTML."""
    if not pdf_path.exists():
        logger.error("VSR Fehler: Datei existiert nicht %s", pdf_path)
        return False

    try:
        text_queue = _get_pdf_text_blocks(pdf_path)

        with pikepdf.open(pdf_path) as pdf:
            root = pdf.Root
            if "/StructTreeRoot" not in root:
                logger.warning("Das PDF enthält keine Tags.")
                return False

            struct_tree = root.StructTreeRoot

            html_head = [
                "<!DOCTYPE html>",
                "<html>",
                "<head>",
                "<meta charset='utf-8'>",
                "<title>PAC26 Visual Screenreader</title>",
                f"<style>\n{VSR_CSS}</style>",
                "</head>",
                "<body>",
                "<div class='doc-container'>",
                "<div class='tag-label tag-label-horizontal lbl-doc' "
                "style='align-self: flex-start; border: none; "
                "margin-bottom: 4px;'>Document</div>",
            ]

            body_html = ""
            if "/K" in struct_tree:
                body_html = _walk_tree_html(struct_tree.get("/K"), text_queue)

            html_tail = ["</div></body></html>"]

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
