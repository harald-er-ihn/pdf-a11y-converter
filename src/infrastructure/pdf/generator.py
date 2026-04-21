# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
PDF Generator Modul (Semantic Overlay Pattern).
Generiert unsichtbaren Text zur semantischen Strukturierung von PDFs.
Behebt Data-Pollution ("0"-Bug) und erzwingt strikte PDF/UA-Rollen
zur Vermeidung von NONSTRUCT-Fragmenten im VSR.
"""

import html
import logging
import os
import re

import fitz  # PyMuPDF
import pikepdf
from weasyprint import HTML as WeasyHTML
from weasyprint.text.fonts import FontConfiguration

from src.domain.spatial import SpatialDOM, SpatialElement
from src.repair import remove_control_characters

logger = logging.getLogger("pdf-converter")

# 1x1 Pixel Transparentes GIF (besser für WeasyPrint als PNG)
PIXEL = (
    "data:image/gif;base64,R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw=="
)

# Diese Typen sind rein topologische Metadaten und dürfen NIEMALS im PDF/UA landen
METADATA_TYPES = {"column", "artifact", "nonstruct"}


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


def _build_element_html(el: SpatialElement) -> str:
    """Generiert den HTML-String für ein einzelnes typisiertes Element."""
    tag = (el.type or "p").lower()

    # 🚀 ARCHITEKTUR-FIX 1: "0"-Bug beheben.
    # Metadaten-Knoten aus der Graph-Fusion filtern wir restlos aus.
    if tag in METADATA_TYPES:
        return ""

    bbox = el.bbox
    w_box = max(bbox[2] - bbox[0], 10.0)
    h_box = max(bbox[3] - bbox[1], 10.0)

    # overflow: visible erlaubt Darstellung von dynamischen BBoxen ohne Abschneiden
    style = (
        f"position: absolute; left: {bbox[0]}pt; top: {bbox[1]}pt; "
        f"width: {w_box}pt; height: {h_box}pt; color: transparent; "
        f"font-size: 8pt; white-space: nowrap; overflow: visible;"
    )

    if tag == "table":
        html_t = remove_control_characters(el.html or "")
        if "<table" in html_t.lower():
            html_t = re.sub(
                r"<table[^>]*>",
                f'<table style="{style}">',
                html_t,
                count=1,
                flags=re.IGNORECASE,
            )
            return html_t + "\n"
        return f'<table style="{style}"><tr><td>{html_t}</td></tr></table>\n'

    if tag in ["list", "ul"]:
        list_html = f'<ul style="{style} margin:0; padding:0; list-style-type:none;">\n'
        for item in el.items or []:
            i_txt = _auto_linkify(
                html.escape(remove_control_characters(item.get("text", "")))
            )
            list_html += f"<li>{i_txt}</li>\n"
        return list_html + "</ul>\n"

    if tag == "note":
        txt = _auto_linkify(html.escape(remove_control_characters(el.text or "")))
        # 🚀 ARCHITEKTUR-FIX 2: role="Note" erzwingt das PDF/UA <Note> Tag,
        # was den NONSTRUCT Bug behebt.
        return f'<div role="Note" style="{style}">{txt}</div>\n'

    if tag == "caption":
        txt = _auto_linkify(html.escape(remove_control_characters(el.text or "")))
        return f'<div role="Caption" style="{style}">{txt}</div>\n'

    if tag == "figure":
        alt_txt = html.escape(remove_control_characters(el.alt_text or "Abbildung"))
        # 🚀 ARCHITEKTUR-FIX 3: Verschachtelung für sauberes Figure-Tagging.
        # WeasyPrint braucht ein explizites <img> für <Figure>.
        return f'<figure style="{style}"><img src="{PIXEL}" alt="{alt_txt}" style="width:100%; height:100%;"/></figure>\n'

    if tag == "formula":
        txt = _auto_linkify(html.escape(remove_control_characters(el.text or "")))
        style_math = style.replace("white-space: nowrap;", "white-space: normal;")
        # Rolle 'math' wird von WeasyPrint zu <Formula> in PDF/UA-1 konvertiert.
        return f'<div role="math" style="{style_math}">{txt}</div>\n'

    if tag not in ["h1", "h2", "h3", "h4", "h5", "h6", "p", "div"]:
        tag = "p"

    text = el.text or ""
    if not text.strip():
        return ""

    clean_txt = _auto_linkify(html.escape(remove_control_characters(text)))
    return f'<{tag} style="{style}">{clean_txt}</{tag}>\n'


def _create_html_document(spatial_dom: SpatialDOM, docinfo: dict, doc_lang: str) -> str:
    """Baut das komplette HTML für WeasyPrint aus dem SpatialDOM auf."""
    html_pages = []
    for page in spatial_dom.pages:
        w, h = page.width, page.height
        p_html = f"<div class='pdf-page' style='width: {w}pt; height: {h}pt;'>"
        for el in page.elements:
            p_html += _build_element_html(el)
        html_pages.append(p_html + "</div>\n")

    doc_w = spatial_dom.pages[0].width if spatial_dom.pages else 595.0
    doc_h = spatial_dom.pages[0].height if spatial_dom.pages else 842.0

    raw_t = str(docinfo.get("/Title", "")).strip("() ")
    raw_title = raw_t or "Barrierefreies Dokument"
    title_text = html.escape(raw_title)

    return (
        f"<!DOCTYPE html>\n<html lang='{doc_lang}'>\n<head>\n"
        f"  <title>{title_text}</title>\n  <style>\n"
        f"      @page {{ margin: 0; size: {doc_w}pt {doc_h}pt; }}\n"
        f"      body {{ margin: 0; padding: 0; font-family: sans-serif; }}\n"
        f"      .pdf-page {{ page-break-after: always; position: relative; }}\n"
        f"      * {{ border: none !important; "
        f"background: transparent !important; "
        f"color: transparent !important; "
        f"text-decoration: none !important; }}\n"
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
    """Semantic Overlay Pattern via WeasyPrint (Typsicher)."""
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

    logger.info("🤖 Verschmelze Original mit barrierefreiem Strukturbaum...")

    raw_t = str(original_docinfo.get("/Title", "")).strip("() ")
    raw_title = raw_t or "Barrierefreies Dokument"
    _merge_pdfs(bg_pdf_path, temp_weasy, output_path, html.escape(raw_title), doc_lang)

    if os.path.exists(temp_weasy):
        os.remove(temp_weasy)
    if os.path.exists(temp_raster):
        os.remove(temp_raster)

    logger.info("✅ Visual Fidelity Prozess komplett abgeschlossen!")
    return True
