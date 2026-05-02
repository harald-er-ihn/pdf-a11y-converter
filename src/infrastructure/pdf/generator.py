# src/infrastructure/pdf/generator.py
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
PDF Generator Modul (Semantic Overlay Pattern).
Nutzt Self-Healing-Graphen für 100% PDF/UA-1 konformes Tagging,
integriert automatische MathML Erzeugung und veraPDF RoleMaps.
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

# METADATA_TYPES filtern rein optische/technische Inhalte aus dem Screenreader Flow
METADATA_TYPES = {"column", "artifact"}

PIXEL = (
    "data:image/gif;base64,R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw=="
)


def _auto_linkify(text: str) -> str:
    """Verlinkt URLs und E-Mails automatisch."""
    text = re.sub(r"(https?://[^\s<]+)", r'<a href="\1">\1</a>', text)
    text = re.sub(r"(?<!/)(www\.[^\s<]+)", r'<a href="http://\1">\1</a>', text)
    return re.sub(
        r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
        r'<a href="mailto:\1">\1</a>',
        text,
    )


def _get_mathml(latex_text: str) -> str:
    """Versucht formatierten LaTeX-Text in Screenreader-freundliches MathML zu konvertieren."""
    try:
        from latex2mathml.converter import convert  # pylint: disable=import-outside-toplevel

        cleaned = re.sub(r"^(\$\$|\\\[|\\\()|(\$\$|\\\]|\\\))$", "", latex_text).strip()
        return convert(cleaned)
    except ImportError:
        pass
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.debug("MathML Konvertierung fehlgeschlagen: %s", e)
    return ""


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


def _heal_heading_hierarchy(spatial_dom: SpatialDOM) -> None:
    """
    Self-Healing-Algorithmus für den Strukturbaum.
    Erzwingt H1 am Anfang und repariert übersprungene Ebenen.
    """
    current_lvl = 0
    for page in spatial_dom.pages:
        for el in page.elements:
            tag = (el.type or "p").strip().lower()
            if tag in METADATA_TYPES:
                continue
            if tag.startswith("h") and len(tag) == 2 and tag[1].isdigit():
                lvl = int(tag[1])
                if current_lvl == 0 and lvl != 1:
                    lvl = 1
                elif lvl > current_lvl + 1:
                    lvl = current_lvl + 1
                el.type = f"h{lvl}"
                current_lvl = lvl


def _build_element_html(el: SpatialElement) -> str:
    """Konstruiert das HTML mit der pac-* DSL für saubere PDF/UA-Tags."""
    tag = (el.type or "p").strip().lower()

    if tag in METADATA_TYPES:
        return ""

    bbox = el.bbox
    w_box = max(bbox[2] - bbox[0], 10.0)
    h_box = max(bbox[3] - bbox[1], 10.0)

    c_style = (
        f"position: absolute; left: {bbox[0]}pt; top: {bbox[1]}pt; "
        f"width: {w_box}pt; height: {h_box}pt;"
    )
    i_style = (
        "margin: 0; padding: 0; color: transparent; "
        "font-size: 8pt; white-space: normal; display: block;"
    )

    text = el.text or ""
    clean_txt = _auto_linkify(html.escape(remove_control_characters(text)))

    wrapper_start = f'<div style="{c_style}">'
    wrapper_end = "</div>\n"

    if tag == "table":
        html_t = remove_control_characters(el.html or "")
        cap_html = ""
        if el.items:
            raw_cap = el.items[0].get("text") or ""
            cap_txt = html.escape(remove_control_characters(raw_cap))
            cap_html = f"<caption>{cap_txt}</caption>"

        if "<th" in html_t.lower() or "<td" in html_t.lower():
            html_t = re.sub(
                r"(<(th|td)[^>]*>)\s*(</\2>)",
                r"\1&#8203;\3",
                html_t,
                flags=re.IGNORECASE,
            )

        tbl_style = f"{i_style} border-collapse: collapse; width:100%;"
        if "<table" in html_t.lower():
            html_t = re.sub(
                r"<table[^>]*>",
                f'<table style="{tbl_style}">{cap_html}',
                html_t,
                count=1,
                flags=re.IGNORECASE,
            )
            return f"{wrapper_start}{html_t}{wrapper_end}"
        return (
            f"{wrapper_start}"
            f'<table style="{tbl_style}">'
            f"{cap_html}<tr><td>{clean_txt}</td></tr></table>{wrapper_end}"
        )

    if tag in ["list", "ul", "ol"]:
        list_html = f'<ul style="{i_style} list-style:none;">\n'
        for item in el.items or []:
            raw_i = item.get("text") or ""
            i_txt = _auto_linkify(html.escape(remove_control_characters(raw_i)))
            list_html += f"<li>{i_txt}</li>\n"
        list_html += "</ul>\n"
        return f"{wrapper_start}{list_html}{wrapper_end}"

    if tag == "note":
        return (
            f"{wrapper_start}"
            f'<pac-note aria-label="{clean_txt}" style="{i_style}">'
            f"{clean_txt}</pac-note>{wrapper_end}"
        )

    if tag == "caption":
        return (
            f"{wrapper_start}"
            f'<pac-caption style="{i_style}">{clean_txt}</pac-caption>'
            f"{wrapper_end}"
        )

    if tag == "figure":
        alt_t = html.escape(
            remove_control_characters(el.alt_text or el.text or "Abbildung")
        )
        fig_html = (
            f'<img src="{PIXEL}" alt="{alt_t}" title="{alt_t}" '
            f'style="{i_style} width:10px; height:10px; display:block;">'
        )
        if el.items:
            raw_cap = el.items[0].get("text") or ""
            cap_txt = html.escape(remove_control_characters(raw_cap))
            fig_html += f'<pac-caption style="{i_style}">{cap_txt}</pac-caption>'
        return f"{wrapper_start}{fig_html}{wrapper_end}"

    if tag == "form":
        txt = html.escape(remove_control_characters(el.text or "Formularfeld"))
        return (
            f"{wrapper_start}"
            f'<pac-form aria-label="{txt}" style="{i_style}">{txt}</pac-form>'
            f"{wrapper_end}"
        )

    if tag == "formula":
        mathml = _get_mathml(text)
        mathml_attr = f' data-mathml="{html.escape(mathml)}"' if mathml else ""
        return (
            f"{wrapper_start}"
            f'<pac-formula title="{clean_txt}" aria-label="{clean_txt}"{mathml_attr} '
            f'style="{i_style} white-space: nowrap;">{clean_txt}'
            f"</pac-formula>{wrapper_end}"
        )

    if tag not in ["h1", "h2", "h3", "h4", "h5", "h6", "p", "blockquote"]:
        tag = "p"

    if not text.strip():
        return ""

    return f'{wrapper_start}<{tag} style="{i_style}">{clean_txt}</{tag}>{wrapper_end}'


def _create_html_document(
    spatial_dom: SpatialDOM, docinfo: Dict[str, Any], doc_lang: str
) -> str:
    _heal_heading_hierarchy(spatial_dom)

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
        f"      * {{ border: none !important; background: transparent "
        f"!important; color: transparent !important; text-decoration: none "
        f"!important; }}\n"
        f"  </style>\n</head>\n<body>\n  {''.join(html_pages)}\n</body>\n"
        f"</html>\n"
    )


def _apply_pdfua_fixes(pdf: pikepdf.Pdf) -> None:
    """
    Behebt architektonische Fehler im StructTreeRoot und fügt RoleMaps ein.
    """
    if "/StructTreeRoot" not in pdf.Root:
        return

    root = pdf.Root.StructTreeRoot

    # RoleMap für veraPDF-Konformität nicht-standardisierter Tags einfügen
    if "/RoleMap" not in root:
        root.RoleMap = pikepdf.Dictionary()
    if "/Formula" not in root.RoleMap:
        root.RoleMap["/Formula"] = pikepdf.Name("/Span")

    def walk(element: Any) -> Any:
        if isinstance(element, pikepdf.Array):
            for i in range(len(element)):
                element[i] = walk(element[i])
            return element

        if isinstance(element, pikepdf.Dictionary):
            tag_type = str(element.get("/S", ""))

            # Fix: PDF/UA Rule 7.2 verbietet Table als Kind einer Table.
            if tag_type == "/Table" and "/K" in element:
                kids = (
                    element.K
                    if isinstance(element.K, pikepdf.Array)
                    else pikepdf.Array([element.K])
                )
                new_kids = pikepdf.Array()
                has_inner = False

                for kid in kids:
                    if (
                        isinstance(kid, pikepdf.Dictionary)
                        and kid.get("/S") == "/Table"
                    ):
                        has_inner = True
                        if "/K" in kid:
                            ikids = (
                                kid.K
                                if isinstance(kid.K, pikepdf.Array)
                                else pikepdf.Array([kid.K])
                            )
                            new_kids.extend(ikids)
                    else:
                        new_kids.append(kid)

                if has_inner:
                    element.K = new_kids

            if "/K" in element:
                element.K = walk(element.K)

            return element

        return element

    if "/K" in root:
        root.K = walk(root.K)


def _merge_pdfs(
    bg_path: str, weasy_path: str, out_path: str, title: str, lang: str
) -> None:
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

                xobj_bytes = (
                    f"/Artifact <</Type /Pagination>> BDC\nq\n{xobj_name} Do\nQ\nEMC\n"
                ).encode("utf-8")
                xobj_str = overlay.make_stream(xobj_bytes)

                old_contents = weasy_page.Contents
                new_array = pikepdf.Array([tr_start])
                if isinstance(old_contents, pikepdf.Array):
                    new_array.extend(old_contents)
                else:
                    new_array.append(old_contents)
                new_array.extend([tr_end, xobj_str])
                weasy_page.Contents = new_array

        _apply_pdfua_fixes(overlay)

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
