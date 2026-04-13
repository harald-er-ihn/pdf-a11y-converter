# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Isolierter Fallback Worker für die Layout-Erkennung (Marker).
Wird vom Orchestrator nur aufgerufen, wenn Docling scheitert.
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

logger = setup_worker_logging("layout-marker")
configure_torch_runtime()


def extract_with_marker(input_path: Path, output_dir: Path) -> Dict[str, Any]:
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

    del artifacts
    del converter

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
    parser = argparse.ArgumentParser(description="Layout Worker (Fallback/Marker)")
    parser.add_argument("--input", required=True, help="Pfad zum Eingabe-PDF")
    parser.add_argument("--output", required=True, help="Pfad zur Ausgabe-JSON")
    args, _ = parser.parse_known_args()

    input_pdf = Path(args.input)
    out_file = Path(args.output)
    out_dir = out_file.parent

    if not input_pdf.exists():
        logger.error("Eingabedatei nicht gefunden: %s", input_pdf)
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        data = extract_with_marker(input_pdf, out_dir)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("✅ Layout-Extraktion (Marker) erfolgreich.")

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("❌ Fataler Fehler in Marker: %s", e)
        write_error_contract(out_file, type(e).__name__, str(e))
        sys.exit(1)
    finally:
        cleanup_memory(aggressive=True)


if __name__ == "__main__":
    main()
