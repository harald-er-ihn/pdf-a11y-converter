# workers/vision_worker/run_vision.py
# PDF A11y Converter - Vision Worker
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Isolierter Worker für die Bildbeschreibung (BLIP).
100% Offline: Gibt klare Fehlermeldungen zurück, falls Modelle fehlen.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# 🚀 OFFLINE-MODE ERZWINGEN
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

WORKER_ROOT = Path(__file__).resolve().parent.parent
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

PROJECT_ROOT = WORKER_ROOT.parent
LOCAL_MODEL_DIR = PROJECT_ROOT / "resources" / "models" / "blip"

from common import (
    cleanup_memory,
    configure_torch_runtime,
    setup_worker_logging,
    write_error_contract,
)

logger = setup_worker_logging("vision-worker")
configure_torch_runtime()

import torch
from PIL import Image
from transformers import BlipForConditionalGeneration, BlipProcessor


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

    logger.info("🤖 Lade Vision-Experten (BLIP) lokal aus: %s", LOCAL_MODEL_DIR.name)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    # ARCHITEKTUR-FIX: Actionable Error Message für 100% Offline-Betrieb
    if not LOCAL_MODEL_DIR.exists():
        msg = (
            f"Lokales Modell fehlt in {LOCAL_MODEL_DIR}. "
            "Bitte fuehre 'python tools/download_models.py' aus, "
            "um die benoetigten Offline-Modelle herunterzuladen."
        )
        logger.error("❌ %s", msg)
        write_error_contract(output_json, "ModelNotFound", msg)
        sys.exit(1)

    model = None
    processor = None

    try:
        processor = BlipProcessor.from_pretrained(
            str(LOCAL_MODEL_DIR), local_files_only=True
        )
        model = (
            BlipForConditionalGeneration.from_pretrained(
                str(LOCAL_MODEL_DIR), local_files_only=True
            )
            .to(device)
            .eval()
        )

        results = {}
        for img_name, img_path_str in images_dict.items():
            img_path = Path(img_path_str)
            if not img_path.exists():
                results[img_name] = "Bild"
                continue

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

    except Exception as e:
        if "OutOfMemoryError" in type(e).__name__:
            write_error_contract(
                output_json, "OutOfMemory", "Grafikkartenspeicher (VRAM) ist voll."
            )
        else:
            write_error_contract(output_json, type(e).__name__, str(e))
        sys.exit(1)
    finally:
        del model
        del processor
        cleanup_memory(aggressive=True)


if __name__ == "__main__":
    main()
