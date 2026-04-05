# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Isolierter Worker für Unterschriften-Erkennung (YOLOv8s).
Nutzt ein lokales, GPL-kompatibles Modell (Tech4Humans).
100% Offline-Betrieb. Keine Cloud-Abhängigkeit.
Wendet die injizierte Precision via `half=True` Flag in Ultralytics an.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict

import fitz  # PyMuPDF
from PIL import Image
from ultralytics import YOLO

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S"
)
logger = logging.getLogger("signature-worker")


def get_signature_model() -> Path:
    """
    Ermittelt den Pfad zum lokalen YOLO-Modell.
    """
    if getattr(sys, "frozen", False):
        base_dir = Path(sys._MEIPASS)  # type: ignore # pylint: disable=protected-access
    else:
        base_dir = Path(__file__).resolve().parent.parent.parent

    model_path = base_dir / "resources" / "models" / "yolov8s_signature.pt"

    if not model_path.exists():
        raise FileNotFoundError(f"Lokales Modell fehlt: {model_path}")

    return model_path


def extract_signatures(pdf_path: Path) -> Dict[str, Any]:
    """
    Rendert PDF-Seiten und nutzt lokales YOLOv8s für Signaturen.
    """
    spatial_data: Dict[str, Any] = {"pages": []}

    # Precision Flag auslesen (YOLO braucht einen Boolean für Half-Precision)
    mode = os.getenv("PDF_A11Y_PRECISION", "fp32")
    use_half = mode in ["fp16", "bf16"]

    try:
        model_path = get_signature_model()
        model = YOLO(str(model_path))
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning(
            "⚠️ Graceful Degradation: Signatur-Erkennung übersprungen (%s)", e
        )
        return spatial_data

    try:
        with fitz.open(pdf_path) as doc:
            for page_num, page in enumerate(doc, start=1):
                # 144 DPI (Scale 2.0) für optimale YOLO-Erkennung
                mat = fitz.Matrix(2.0, 2.0)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                # Modell Inference (mit Half-Precision falls von Engine injiziert)
                results = model(img, verbose=False, half=use_half)
                elements = []

                for result in results:
                    boxes = result.boxes
                    for box in boxes:
                        # BBox extrahieren [x1, y1, x2, y2]
                        coords = box.xyxy[0].tolist()

                        # Skalierung zurückrechnen (144 DPI -> 72 DPI)
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
                        {
                            "page_num": page_num,
                            "elements": elements,
                        }
                    )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Fehler bei der Signatur-Extraktion: %s", e)

    return spatial_data


def main() -> None:
    """Haupteinstiegspunkt für den Signature-Worker."""
    parser = argparse.ArgumentParser(description="Signature (Lokales YOLO)")
    parser.add_argument("--input", required=True, help="Pfad zum PDF")
    parser.add_argument("--output", required=True, help="Ausgabe-JSON")
    args = parser.parse_args()

    input_pdf = Path(args.input)
    output_json = Path(args.output)

    if not input_pdf.exists():
        logger.error("❌ Eingabedatei nicht gefunden: %s", input_pdf)
        sys.exit(1)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    logger.info("🤖 Signature-Worker analysiert %s...", input_pdf.name)

    extracted = extract_signatures(input_pdf)

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(extracted, f, ensure_ascii=False, indent=2)

    sig_count = sum(len(p.get("elements", [])) for p in extracted.get("pages", []))
    logger.info("✅ %s Unterschrift(en) erfolgreich extrahiert.", sig_count)


if __name__ == "__main__":
    main()
