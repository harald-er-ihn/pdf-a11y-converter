# src/infrastructure/pdf/generator.py
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
PDF Generator Modul (Semantic Overlay Pattern).
Generiert unsichtbaren Text zur semantischen Strukturierung von PDFs.
Baut valides HTML5 für 100% PDF/UA-1 konformes Tagging durch WeasyPrint.
"""

import html
import logging
import os
import re
from typing import Any, Dict

import fitz  # PyMuPDF
import pikepdf
from weasyprint import HTML as WeasyHTML
from weasyprint.text.fonts import FontConfiguration

from src.domain.spatial import SpatialDOM, SpatialElement
from src.repair import remove_control_characters

logger = logging.getLogger("pdf-converter")

# Ein transparentes Pixel erzwingt die Erstellung der Bounding Box im PDF/UA
PIXEL = (
    "data:image/gif;base64,R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw=="
)

METADATA_TYPES = {"column", "artifact", "nonstruct"}


def _auto_linkify(text: str) -> str:
    """Verlinkt URLs und E-Mails automatisch."""
    text = re.sub(r"(https?://[^\s<]+)", r'<a href="\1">\1</a>', text)
    text = re.sub(r"(?<!/)(www\.[^\s<]+)", r'<a href="http://\1">\1</a>', text)
    return re.sub(
        r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
        r'<a href="mailto:\1">\1</a>',
        text,
    )


def _rasterize_and_compress_pdf(input_pdf: str, temp_out: str) -> None:
    """Rastert das Dokument als Fallback bei defekten Fonts."""
    logger.warning("⚠️ Ghost-Font Fix: Rastere (Ultra Compression)...")
    doc_orig = fitz.open(input_pdf)
    doc_raster = fitz.open()

    for page_num in range(len(doc_orig)):
        page_orig = doc_orig.load_page(page_num)
        pix = page_orig.get_pixmap(dpi=144, alpha=False)
        img_bytes = pix.tobytes("jpeg", 65)
        rect = page_orig.rect
        page_new = doc_raster.new_page(width=rect.width, height=rect.height)
        page_new.insert_image(rect, stream=img_bytes)

    doc_raster.save(temp_out, garbage=4, deflate=True, clean=True)
    doc_raster.close()
    doc_orig.close()


def _build_element_html(el: SpatialElement) -> str:
    """Konstruiert das HTML-Element unter Erhalt spezifischer Artefakte."""
    tag = (el.type or "p").lower()

    if tag in METADATA_TYPES:
        return ""

    bbox = el.bbox
    w_box = max(bbox[2] - bbox[0], 10.0)
    h_box = max(bbox[3] - bbox[1], 10.0)

    style = (
        f"position: absolute; left: {bbox[0]}pt; top: {bbox[1]}pt; "
        f"width: {w_box}pt; height: {h_box}pt; color: transparent; "
        f"font-size: 8pt; white-space: normal; overflow: visible;"
    )

    text = el.text or ""
    clean_txt = _auto_linkify(html.escape(remove_control_characters(text)))

    if tag == "table":
        html_t = remove_control_characters(el.html or "")
        caption_html = ""
        if el.items:
            cap_txt = html.escape(
                remove_control_characters(el.items[0].get("text", ""))
            )
            caption_html = f"<caption>{cap_txt}</caption>"

        if "<table" in html_t.lower():
            html_t = re.sub(
                r"<table[^>]*>",
                f'<table style="{style} border-collapse: collapse;">{caption_html}',
                html_t,
                count=1,
                flags=re.IGNORECASE,
            )
            return html_t + "\n"
        return (
            f'<table style="{style} border-collapse: collapse;">'
            f"{caption_html}<tr><td>{clean_txt}</td></tr></table>\n"
        )

    if tag in ["list", "ul", "ol"]:
        list_html = f'<ul style="{style} margin:0; padding:0; list-style:none;">\n'
        for item in el.items or []:
            i_txt = _auto_linkify(
                html.escape(remove_control_characters(item.get("text", "")))
            )
            list_html += f"<li>{i_txt}</li>\n"
        return list_html + "</ul>\n"

    if tag == "note":
        return f'<div role="note" style="{style}">{clean_txt}</div>\n'

    if tag == "caption":
        return f'<div role="caption" style="{style}">{clean_txt}</div>\n'

    if tag == "figure":
        alt_txt = html.escape(remove_control_characters(el.alt_text or "Abbildung"))
        fig_html = f'<img src="{PIXEL}" alt="{alt_txt}" style="width:100%;">'
        if el.items:
            cap_txt = html.escape(
                remove_control_characters(el.items[0].get("text", ""))
            )
            fig_html += f"<figcaption>{cap_txt}</figcaption>"
        return f'<figure style="{style} margin:0;">{fig_html}</figure>\n'

    if tag == "form":
        txt = html.escape(remove_control_characters(el.text or "Formularfeld"))
        # ARCHITEKTUR-FIX: Sauberes HTML Input Field zwingt WeasyPrint zum <Form> Tag
        return (
            f'<form style="{style} margin:0;">'
            f'<input type="text" aria-label="{txt}" title="{txt}" value="{txt}">'
            f"</form>\n"
        )

    if tag == "formula":
        # ARCHITEKTUR-FIX: Semantisches MathML Tag für <Formula>
        return f'<math style="{style} display:block;" alt="{clean_txt}">{clean_txt}</math>\n'

    if tag not in ["h1", "h2", "h3", "h4", "h5", "h6", "p", "div"]:
        tag = "p"

    if not text.strip():
        return ""

    return f'<{tag} style="{style}">{clean_txt}</{tag}>\n'


def _create_html_document(
    spatial_dom: SpatialDOM, docinfo: Dict[str, Any], doc_lang: str
) -> str:
    """Baut das unsichtbare HTML5 Grid auf."""
    html_pages = []
    for page in spatial_dom.pages:
        w, h = page.width, page.height
        p_html = f"<div class='pdf-page' style='width: {w}pt; height: {h}pt;'>"
        for el in page.elements:
            p_html += _build_element_html(el)
        html_pages.append(p_html + "</div>\n")

    doc_w = spatial_dom.pages[0].width if spatial_dom.pages else 595.0
    doc_h = spatial_dom.pages[0].height if spatial_dom.pages else 842.0
    raw_title = str(docinfo.get("/Title", "")).strip("() ") or "Dokument"

    return (
        f"<!DOCTYPE html>\n<html lang='{doc_lang}'>\n<head>\n"
        f"  <title>{html.escape(raw_title)}</title>\n  <style>\n"
        f"      @page {{ margin: 0; size: {doc_w}pt {doc_h}pt; }}\n"
        f"      body {{ margin: 0; padding: 0; font-family: sans-serif; }}\n"
        f"      .pdf-page {{ page-break-after: always; position: relative; }}\n"
        f"      * {{ border: none !important; background: transparent !important; "
        f"color: transparent !important; text-decoration: none !important; }}\n"
        f"  </style>\n</head>\n<body>\n  {''.join(html_pages)}\n</body>\n</html>\n"
    )


def _merge_pdfs(
    bg_path: str, weasy_path: str, out_path: str, title: str, lang: str
) -> None:
    """Kombiniert visuelle Ebene (Original) und semantische Ebene (Weasy)."""
    with pikepdf.open(bg_path) as orig, pikepdf.open(weasy_path) as overlay:
        for i, weasy_page in enumerate(overlay.pages):
            if i < len(orig.pages):
                orig_page = orig.pages[i]
                weasy_page.Tabs = pikepdf.Name("/S")
                xobj_name = weasy_page.add_resource(
                    orig_page.as_form_xobject(), pikepdf.Name("/XObject")
                )
                tr_start = overlay.make_stream(b"q 3 Tr\n")
                tr_end = overlay.make_stream(b"\nQ\n")
                xobj_str = overlay.make_stream(
                    f"/Artifact <</Type /Pagination>> BDC\nq\n"
                    f"{xobj_name} Do\nQ\nEMC\n".encode("utf-8")
                )

                old_contents = weasy_page.Contents
                new_array = pikepdf.Array([tr_start])
                if isinstance(old_contents, pikepdf.Array):
                    new_array.extend(old_contents)
                else:
                    new_array.append(old_contents)
                new_array.extend([tr_end, xobj_str])
                weasy_page.Contents = new_array

        with pikepdf.open(bg_path) as p_orig:
            with (
                p_orig.open_metadata(set_pikepdf_as_editor=False) as o_meta,
                overlay.open_metadata(set_pikepdf_as_editor=False) as n_meta,
            ):
                for k, v in o_meta.items():
                    if v is not None:
                        try:
                            n_meta[k] = v
                        except Exception:
                            pass
                n_meta["dc:title"] = title

        if "/ViewerPreferences" not in overlay.Root:
            overlay.Root.ViewerPreferences = pikepdf.Dictionary()
        overlay.Root.ViewerPreferences.DisplayDocTitle = pikepdf.Boolean(True)
        overlay.Root.Lang = pikepdf.String(lang)
        overlay.save(
            out_path,
            compress_streams=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
        )


def generate_pdf_from_spatial(
    spatial_dom: SpatialDOM,
    input_pdf_path: str,
    images_dict: dict,
    output_path: str,
    original_docinfo: dict,
    doc_lang: str,
) -> bool:
    """Haupt-Facade für den Generator-Prozess."""
    logger.info("🤖 Generiere unsichtbaren Layer (Semantic Overlay)...")
    full_html = _create_html_document(spatial_dom, original_docinfo, doc_lang)
    temp_weasy = str(output_path).replace(".pdf", "_temp_weasy.pdf")
    WeasyHTML(string=full_html, base_url=os.getcwd()).write_pdf(
        temp_weasy, font_config=FontConfiguration(), pdf_variant="pdf/ua-1"
    )

    bg_pdf_path = str(input_pdf_path)
    temp_raster = str(output_path).replace(".pdf", "_temp_rasterized.pdf")

    if spatial_dom.needs_visual_reconstruction:
        _rasterize_and_compress_pdf(str(input_pdf_path), temp_raster)
        bg_pdf_path = temp_raster

    raw_title = str(original_docinfo.get("/Title", "")).strip("() ")
    safe_title = html.escape(raw_title or "Barrierefreies Dokument")

    _merge_pdfs(bg_pdf_path, temp_weasy, output_path, safe_title, doc_lang)

    if os.path.exists(temp_weasy):
        os.remove(temp_weasy)
    if os.path.exists(temp_raster):
        os.remove(temp_raster)
    logger.info("✅ Visual Fidelity Prozess komplett abgeschlossen!")
    return True
