# PDF A11y Converter - Vision Worker
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Isolierter Worker für die Bildbeschreibung (BLIP).
Gibt die Ergebnisse strikt als JSON zurück.
"""

import argparse
import json
import sys
from pathlib import Path

# 🚀 SYSTEM-PATH FIX: Erlaubt den Import von 'common', ohne dass wir 
# src/ oder das Root-Verzeichnis injizieren müssen!
WORKER_ROOT = Path(__file__).resolve().parent.parent
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

# Jetzt können wir unseren neuen, isolierten Common-Code nutzen
from common import cleanup_memory, configure_torch_runtime, setup_worker_logging

# 1. Logging initialisieren
logger = setup_worker_logging("vision-worker")

# 2. PyTorch & C++ Threads in Ketten legen (Verhindert VM-Freezes)
configure_torch_runtime()

import torch  # pylint: disable=wrong-import-position
from PIL import Image  # pylint: disable=wrong-import-position
from transformers import BlipForConditionalGeneration, BlipProcessor  # pylint: disable=wrong-import-position


def main() -> None:
    parser = argparse.ArgumentParser(description="Vision Worker")
    parser.add_argument("--input", required=True, help="JSON mit Bild-Pfaden")
    parser.add_argument("--output", required=True, help="Ausgabe-JSON für Alt-Texte")
    args = parser.parse_args()

    input_json = Path(args.input)
    output_json = Path(args.output)

    if not input_json.exists():
        logger.error("Eingabedatei nicht gefunden: %s", input_json)
        sys.exit(1)

    with open(input_json, "r", encoding="utf-8") as f:
        images_dict = json.load(f)

    logger.info("🤖 Lade Vision-Experten (BLIP)...")
    model_id = "Salesforce/blip-image-captioning-base"
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("Verwende Hardware: %s", device.upper())

    model = None
    processor = None

    try:
        processor = BlipProcessor.from_pretrained(model_id)
        model = BlipForConditionalGeneration.from_pretrained(model_id).to(device).eval()

        results = {}
        for img_name, img_path_str in images_dict.items():
            img_path = Path(img_path_str)
            if not img_path.exists():
                logger.warning("Bild nicht gefunden: %s", img_path)
                results[img_name] = "Bild"
                continue

            logger.info("Analysiere %s...", img_name)
            with Image.open(img_path) as pil_img:
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

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("❌ Fataler Fehler im Vision-Worker: %s", e)
        sys.exit(1)

    finally:
        # 🚀 ENTERPRISE MEMORY CLEANUP: 
        # Zuerst lokale Referenzen zerstören, DANN aufräumen
        if model is not None:
            del model
        if processor is not None:
            del processor
            
        cleanup_memory(aggressive=True)


if __name__ == "__main__":
    main()
