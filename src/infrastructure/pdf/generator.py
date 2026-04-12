# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
PDF Generator Modul (Semantic Overlay Pattern).
Generiert unsichtbaren Text zur semantischen Strukturierung von PDFs.
"""

import html
import logging
import os
import re
from typing import Dict, Any

import fitz  # PyMuPDF
import pikepdf
from weasyprint import HTML as WeasyHTML
from weasyprint.text.fonts import FontConfiguration

from src.repair import remove_control_characters
from src.infrastructure.validation.validation import check_verapdf

logger = logging.getLogger("pdf-converter")

PIXEL = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAA"
    "AABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAA"
    "SUVORK5CYII="
)


def _auto_linkify(text: str) -> str:
    """Wandelt erkannte URLs und E-Mails in <a> Tags um."""
    text = re.sub(r"(https?://[^\s<]+)", r'<a href="\1">\1</a>', text)
    text = re.sub(r"(?<!/)(www\.[^\s<]+)", r'<a href="http://\1">\1</a>', text)
    return re.sub(
        r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
        r'<a href="mailto:\1">\1</a>',
        text,
    )


def _rasterize_and_compress_pdf(input_pdf_path: str, temp_rasterized: str) -> None:
    """Rastert das Original-PDF (144 DPI) für Ultra-Compression."""
    logger.warning("⚠️ Ghost-Font Fix: Rastere (Ultra Compression)...")
    doc_orig = fitz.open(input_pdf_path)
    doc_raster = fitz.open()

    for page_num in range(len(doc_orig)):
        page_orig = doc_orig.load_page(page_num)
        pix = page_orig.get_pixmap(dpi=144, alpha=False)
        img_bytes = pix.tobytes("jpeg", 65)

        rect = page_orig.rect
        page_new = doc_raster.new_page(width=rect.width, height=rect.height)
        page_new.insert_image(rect, stream=img_bytes)

    doc_raster.save(temp_rasterized, garbage=4, deflate=True, clean=True)
    doc_raster.close()
    doc_orig.close()


def _build_element_html(el: Dict[str, Any]) -> str:
    """Generiert den HTML-String für ein einzelnes Element."""
    tag = el.get("type", "p")
    bbox = el.get("bbox", [0, 0, 10, 10])
    w_box, h_box = max(bbox[2] - bbox[0], 10), max(bbox[3] - bbox[1], 10)
    style = (
        f"position: absolute; left: {bbox[0]}pt; top: {bbox[1]}pt; "
        f"width: {w_box}pt; height: {h_box}pt; color: transparent; "
        f"font-size: 8pt; overflow: hidden;"
    )

    if tag == "table":
        html_t = remove_control_characters(el.get("html", ""))
        return f"<div style='{style}'>{html_t}</div>\n"

    if tag == "list":
        list_html = "<ul style='margin:0; padding:0; list-style-type:none;'>\n"
        for item in el.get("items", []):
            ib = item.get("bbox", [0, 0, 10, 10])
            i_sty = (
                f"position: absolute; left: {ib[0]}pt; top: {ib[1]}pt; "
                f"width: {max(ib[2] - ib[0], 10)}pt; height: {max(ib[3] - ib[1], 10)}pt;"
                f" color: transparent; font-size: 8pt; overflow: hidden;"
            )
            i_txt = _auto_linkify(
                html.escape(remove_control_characters(item.get("text", "")))
            )
            list_html += f"<li style='{i_sty}'>{i_txt}</li>\n"
        return list_html + "</ul>\n"

    if tag == "Note":
        txt = _auto_linkify(html.escape(remove_control_characters(el.get("text", ""))))
        return f"<aside role='note' style='{style}'>{txt}</aside>\n"

    if tag == "figure":
        alt_txt = html.escape(
            remove_control_characters(el.get("alt_text", "Abbildung"))
        )
        return f"<img src='{PIXEL}' alt='{alt_txt}' style='{style}'/>\n"

    if tag not in ["h1", "h2", "h3", "h4", "h5", "h6", "p", "div"]:
        tag = "p"

    text = el.get("text", "")
    if not text.strip():
        return ""

    clean_txt = _auto_linkify(html.escape(remove_control_characters(text)))
    return f"<{tag} style='{style}'>{clean_txt}</{tag}>\n"


def _create_html_document(
    spatial_dom: Dict[str, Any], docinfo: dict, doc_lang: str
) -> str:
    """Baut das komplette HTML für WeasyPrint zusammen."""
    html_pages = []
    for page in spatial_dom.get("pages", []):
        w, h = page.get("width", 595.0), page.get("height", 842.0)
        page_html = f"<div class='pdf-page' style='width: {w}pt; height: {h}pt;'>"
        for el in page.get("elements", []):
            page_html += _build_element_html(el)
        html_pages.append(page_html + "</div>\n")

    doc_w = spatial_dom.get("pages", [{}])[0].get("width", 595.0)
    doc_h = spatial_dom.get("pages", [{}])[0].get("height", 842.0)

    raw_title = str(docinfo.get("/Title", "")).strip("() ") or "Barrierefreies Dokument"
    title_text = html.escape(raw_title)

    return (
        f"<!DOCTYPE html>\n<html lang='{doc_lang}'>\n<head>\n"
        f"  <title>{title_text}</title>\n  <style>\n"
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
    """Stempelt das visuelle PDF als Artifact in das strukturelle PDF."""
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
                    f"/Artifact <</Type /Pagination>> BDC\nq\n{xobj_name} Do\nQ\nEMC\n".encode(
                        "utf-8"
                    )
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
    spatial_dom: Dict[str, Any],
    input_pdf_path: str,
    images_dict: dict,
    output_path: str,
    original_docinfo: dict,
    doc_lang: str,
) -> bool:
    """Semantic Overlay Pattern via WeasyPrint."""
    logger.info("🤖 Generiere unsichtbaren Layer (Semantic Overlay)...")

    full_html = _create_html_document(spatial_dom, original_docinfo, doc_lang)
    temp_weasy = str(output_path).replace(".pdf", "_temp_weasy.pdf")

    WeasyHTML(string=full_html, base_url=os.getcwd()).write_pdf(
        temp_weasy, font_config=FontConfiguration(), pdf_variant="pdf/ua-1"
    )

    bg_pdf_path = str(input_pdf_path)
    temp_rasterized = str(output_path).replace(".pdf", "_temp_rasterized.pdf")

    if spatial_dom.get("needs_visual_reconstruction", False):
        _rasterize_and_compress_pdf(str(input_pdf_path), temp_rasterized)
        bg_pdf_path = temp_rasterized

    logger.info("🤖 Verschmelze Original mit barrierefreiem Strukturbaum...")

    raw_title = (
        str(original_docinfo.get("/Title", "")).strip("() ")
        or "Barrierefreies Dokument"
    )
    _merge_pdfs(bg_pdf_path, temp_weasy, output_path, html.escape(raw_title), doc_lang)

    if os.path.exists(temp_weasy):
        os.remove(temp_weasy)
    if os.path.exists(temp_rasterized):
        os.remove(temp_rasterized)

    check_verapdf(output_path, is_final=True)
    logger.info("✅ Visual Fidelity Prozess komplett abgeschlossen!")
    return True
