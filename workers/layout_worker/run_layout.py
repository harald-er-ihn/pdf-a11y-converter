# PDF A11y Converter - Layout Worker
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Isolierter Worker für die Layout-Erkennung.
Nutzt Docling, um Text, Typen (H1, P, etc.) und exakte Bounding Boxes
zu extrahieren. Konvertiert die PDF-Koordinaten in Web-Koordinaten.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S"
)
logger = logging.getLogger("layout-worker")


def _setup_docling(force_ocr: bool) -> Any:
    """Konfiguriert die Docling Pipeline."""
    from docling.datamodel.base_models import InputFormat  # pylint: disable=import-outside-toplevel
    from docling.datamodel.pipeline_options import PdfPipelineOptions  # pylint: disable=import-outside-toplevel
    from docling.document_converter import DocumentConverter, PdfFormatOption  # pylint: disable=import-outside-toplevel

    options = PdfPipelineOptions()
    options.do_ocr = True
    options.do_table_structure = True
    options.generate_picture_images = True

    if force_ocr:
        logger.info("⚠️ FORCE-OCR: Ignoriere PDF-Textlayer und erzwinge Visual OCR.")
        try:
            options.ocr_options.force_full_page_ocr = True
        except Exception as e:
            logger.warning("OcrOptions Anpassung fehlgeschlagen: %s", e)

    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def _extract_images(doc: Any, output_dir: Path) -> Dict[str, str]:
    """Speichert Bilder aus dem Docling-Dokument."""
    images_dict = {}
    if hasattr(doc, "pictures"):
        for idx, picture in enumerate(doc.pictures):
            pil_img = None
            if hasattr(picture, "get_image"):
                try:
                    pil_img = picture.get_image(doc)
                except Exception:
                    pass
            elif hasattr(picture, "image") and picture.image:
                pil_img = picture.image

            if pil_img:
                img_name = f"image_{idx}.png"
                img_path = output_dir / img_name
                pil_img.convert("RGB").save(img_path, format="PNG")
                images_dict[img_name] = str(img_path)
    return images_dict


def _map_docling_type(label_name: str, level: int) -> str:
    """Mappt Docling-Klassen auf unser internes Format."""
    if label_name == "title" or label_name.startswith("heading"):
        return "h" + str(min(level if level > 0 else 1, 6))
    if label_name == "list_item":
        return "li"
    if label_name == "picture":
        return "figure"
    if label_name == "equation":
        return "formula"
    return "p"


def _extract_elements(
    doc: Any, page_heights: Dict[int, float], spatial_dom: Dict
) -> None:
    """Verarbeitet die rohen Docling-Items und webt sie in das Spatial-DOM ein."""
    for item, level in doc.iterate_items():
        try:
            if not hasattr(item, "prov") or not item.prov:
                continue

            prov = item.prov[0]
            if not hasattr(prov, "bbox"):
                continue

            p_num = prov.page_no
            p_h = page_heights.get(p_num, 842.0)
            bbox = [prov.bbox.l, p_h - prov.bbox.t, prov.bbox.r, p_h - prov.bbox.b]

            text = getattr(item, "text", "")
            el_type = _map_docling_type(item.label.name, level)

            if not text and el_type not in ["figure", "formula"]:
                continue

            for page in spatial_dom["pages"]:
                if page["page_num"] == p_num:
                    page["elements"].append(
                        {"type": el_type, "text": text, "bbox": bbox}
                    )
                    break
        except Exception as e:
            logger.debug("Element übersprungen: %s", e)


def extract_spatial_data_docling(
    input_path: Path, output_dir: Path, force_ocr: bool = False
) -> Dict[str, Any]:
    """Extrahiert Text, Typen und exakte Top-Left Koordinaten via Docling."""
    logger.info("Starte räumliche Docling-Analyse (Spatial Data)...")

    converter = _setup_docling(force_ocr)
    result = converter.convert(input_path)
    doc = result.document

    spatial_dom: Dict[str, Any] = {
        "pages": [],
        "images": _extract_images(doc, output_dir),
    }
    page_heights = {}

    for page_no, page_info in doc.pages.items():
        w = page_info.size.width if hasattr(page_info, "size") else 595.0
        h = page_info.size.height if hasattr(page_info, "size") else 842.0
        page_heights[page_no] = h
        spatial_dom["pages"].append(
            {"page_num": page_no, "width": w, "height": h, "elements": []}
        )

    _extract_elements(doc, page_heights, spatial_dom)

    return spatial_dom


def extract_with_marker_fallback(input_path: Path, output_dir: Path) -> Dict[str, Any]:
    """Fallback: Wenn Docling crasht, liefert Marker eine flache Struktur."""
    import marker.models  # pylint: disable=import-outside-toplevel
    from marker.converters.pdf import PdfConverter  # pylint: disable=import-outside-toplevel

    logger.info("Starte Marker-Fallback (Flat Spatial DOM)...")
    artifacts = {}
    for name in ["load_all_models", "load_models", "create_model_dict"]:
        if hasattr(marker.models, name):
            artifacts = getattr(marker.models, name)()
            break

    converter = PdfConverter(artifact_dict=artifacts)
    rendered = converter(str(input_path))

    images_dict = {}
    for img_name, pil_img in getattr(rendered, "images", {}).items():
        img_path = output_dir / img_name
        pil_img.convert("RGB").save(img_path, format="PNG")
        images_dict[img_name] = str(img_path)

    return {
        "pages": [
            {
                "page_num": 1,
                "width": 595.0,
                "height": 842.0,
                "elements": [
                    {"type": "p", "text": rendered.markdown, "bbox": [0, 0, 595, 842]}
                ],
            }
        ],
        "images": images_dict,
    }


def main() -> None:
    """Haupteinstiegspunkt."""
    parser = argparse.ArgumentParser(description="Layout Worker (Spatial)")
    parser.add_argument("--input", required=True, help="Pfad zum Eingabe-PDF")
    parser.add_argument("--output", required=True, help="Pfad zur Ausgabe-JSON")
    parser.add_argument("--force-ocr", action="store_true", help="Erzwingt OCR")
    args, _ = parser.parse_known_args()

    input_pdf = Path(args.input)
    out_dir = Path(args.output).parent

    if not input_pdf.exists():
        logger.error("Eingabedatei nicht gefunden: %s", input_pdf)
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        data = extract_spatial_data_docling(input_pdf, out_dir, args.force_ocr)
    except Exception as e:
        logger.warning("Docling fehlgeschlagen: %s", e)
        try:
            data = extract_with_marker_fallback(input_pdf, out_dir)
        except Exception as ex:
            logger.error("❌ Layout-Extraktion fehlgeschlagen: %s", ex)
            sys.exit(1)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info("Layout-Extraktion erfolgreich abgeschlossen.")


if __name__ == "__main__":
    main()
