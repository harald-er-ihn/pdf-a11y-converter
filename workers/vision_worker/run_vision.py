# PDF A11y Converter - Vision Worker
# Copyright (C) 2026 Dr. Harald Hutter
"""
Isolierter Worker für die Bildbeschreibung (BLIP).
Gibt die Ergebnisse strikt als JSON zurück.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import torch
from PIL import Image
from transformers import BlipForConditionalGeneration, BlipProcessor

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S"
)
logger = logging.getLogger("vision-worker")


def main() -> None:
    parser = argparse.ArgumentParser(description="Vision Worker")
    parser.add_argument("--input", required=True, help="JSON mit Bild-Pfaden")
    parser.add_argument("--output", required=True, help="Ausgabe-JSON für Alt-Texte")
    args = parser.parse_args()

    input_json = Path(args.input)
    output_json = Path(args.output)

    if not input_json.exists():
        logger.error(f"Eingabedatei nicht gefunden: {input_json}")
        sys.exit(1)

    with open(input_json, "r", encoding="utf-8") as f:
        images_dict = json.load(f)

    logger.info("🤖 Lade Vision-Experten (BLIP)...")
    model_id = "Salesforce/blip-image-captioning-base"
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Verwende Hardware: {device.upper()}")

    try:
        processor = BlipProcessor.from_pretrained(model_id)
        model = BlipForConditionalGeneration.from_pretrained(model_id).to(device).eval()

        results = {}
        for img_name, img_path_str in images_dict.items():
            img_path = Path(img_path_str)
            if not img_path.exists():
                logger.warning(f"Bild nicht gefunden: {img_path}")
                results[img_name] = "Bild"
                continue

            logger.info(f"Analysiere {img_name}...")
            with Image.open(img_path) as pil_img:
                # Bild in RGB konvertieren (verhindert Fehler bei Graustufen/RGBA)
                pil_img = pil_img.convert("RGB")
                inputs = processor(pil_img, return_tensors="pt").to(device)

                with torch.no_grad():
                    output = model.generate(**inputs, max_new_tokens=40)

                alt_text = processor.decode(
                    output[0], skip_special_tokens=True
                ).capitalize()
                results[img_name] = alt_text

        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        logger.info("✅ Vision-Extraktion erfolgreich abgeschlossen.")

    except Exception as e:
        logger.error(f"❌ Fataler Fehler im Vision-Worker: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
