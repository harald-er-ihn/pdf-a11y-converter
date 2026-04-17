# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Isolierter Worker für Unterschriften-Erkennung (YOLOv8s).
Lädt das Modell zwingend und deterministisch aus dem lokalen resources-Ordner.
"""

import argparse
import json
import sys
import os
from pathlib import Path
from typing import Any, Dict

# 🚀 OFFLINE-MODE ERZWINGEN (verhindert YOLO Telemetrie)
os.environ["YOLO_OFFLINE"] = "True"

# SYSTEM-PATH FIX
WORKER_ROOT = Path(__file__).resolve().parent.parent
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

PROJECT_ROOT = WORKER_ROOT.parent
LOCAL_MODEL_PATH = (
    PROJECT_ROOT / "resources" / "models" / "yolov8" / "yolov8s_signature.pt"
)

from common import cleanup_memory, configure_torch_runtime, setup_worker_logging

logger = setup_worker_logging("signature-worker")
configure_torch_runtime()

import fitz  # PyMuPDF
from PIL import Image
from ultralytics import YOLO


def extract_signatures(pdf_path: Path) -> Dict[str, Any]:
    spatial_data: Dict[str, Any] = {"pages": []}
    model = None

    try:
        if not LOCAL_MODEL_PATH.exists():
            raise FileNotFoundError(f"Lokales Modell fehlt: {LOCAL_MODEL_PATH}")

        # Lädt exakt diese Datei (Offline garantiert)
        model = YOLO(str(LOCAL_MODEL_PATH))

        with fitz.open(pdf_path) as doc:
            for page_num, page in enumerate(doc, start=1):
                mat = fitz.Matrix(2.0, 2.0)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                results = model(img, verbose=False)
                elements = []

                for result in results:
                    for box in result.boxes:
                        coords = box.xyxy[0].tolist()
                        scaled_bbox = [c / 2.0 for c in coords]
                        elements.append(
                            {
                                "type": "figure",
                                "bbox": scaled_bbox,
                                "alt_text": "Signature",
                            }
                        )

                if elements:
                    spatial_data["pages"].append(
                        {"page_num": page_num, "elements": elements}
                    )

    except Exception as e:
        logger.warning("⚠️ Signatur-Erkennung übersprungen (%s)", e)
    finally:
        if model is not None:
            del model
        cleanup_memory(aggressive=True)

    return spatial_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Signature (Lokales YOLO)")
    parser.add_argument("--input", required=True, help="Pfad zum PDF")
    parser.add_argument("--output", required=True, help="Ausgabe-JSON")
    args = parser.parse_args()

    input_pdf = Path(args.input)
    output_json = Path(args.output)

    logger.info("🤖 Signature-Worker analysiert %s...", input_pdf.name)
    extracted = extract_signatures(input_pdf)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(extracted, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
