# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Isolierter Primary Worker für die Layout-Erkennung (Docling).
Extrahiert Text, Typen (H1, P, etc.) und exakte Bounding Boxes.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

# 🚀 SYSTEM-PATH FIX
WORKER_ROOT = Path(__file__).resolve().parent.parent
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from common import (
    cleanup_memory,
    configure_torch_runtime,
    setup_worker_logging,
    write_error_contract,
)

USER_CACHE = Path.home() / ".pdf-a11y-models"
USER_CACHE.mkdir(parents=True, exist_ok=True)

os.environ["HF_HOME"] = str(USER_CACHE / "huggingface")
os.environ["DOCLING_HOME"] = str(USER_CACHE / "docling")
os.environ["DATALAB_CACHE_DIR"] = str(USER_CACHE / "datalab")
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TQDM_DISABLE"] = "1"

logger = setup_worker_logging("layout-docling")
configure_torch_runtime()


def _setup_docling(force_ocr: bool) -> Any:
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
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("OcrOptions Anpassung fehlgeschlagen: %s", e)

    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def _extract_images(doc: Any, output_dir: Path) -> Dict[str, str]:
    images_dict = {}
    if hasattr(doc, "pictures"):
        for idx, picture in enumerate(doc.pictures):
            pil_img = None
            if hasattr(picture, "get_image"):
                try:
                    pil_img = picture.get_image(doc)
                except Exception:  # pylint: disable=broad-exception-caught
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
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.debug("Element übersprungen: %s", e)


def extract_spatial_data_docling(
    input_path: Path, output_dir: Path, force_ocr: bool = False
) -> Dict[str, Any]:
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

    del doc
    del result
    del converter

    return spatial_dom


def main() -> None:
    parser = argparse.ArgumentParser(description="Layout Worker (Primary/Docling)")
    parser.add_argument("--input", required=True, help="Pfad zum Eingabe-PDF")
    parser.add_argument("--output", required=True, help="Pfad zur Ausgabe-JSON")
    parser.add_argument("--force-ocr", action="store_true", help="Erzwingt OCR")
    args, _ = parser.parse_known_args()

    input_pdf = Path(args.input)
    out_file = Path(args.output)
    out_dir = out_file.parent

    if not input_pdf.exists():
        logger.error("Eingabedatei nicht gefunden: %s", input_pdf)
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        data = extract_spatial_data_docling(input_pdf, out_dir, args.force_ocr)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("✅ Layout-Extraktion (Docling) erfolgreich.")

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("❌ Fataler Fehler in Docling: %s", e)
        write_error_contract(out_file, type(e).__name__, str(e))
        sys.exit(1)
    finally:
        cleanup_memory(aggressive=True)


if __name__ == "__main__":
    main()
