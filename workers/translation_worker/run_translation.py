# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Isolierter Worker für KI-Übersetzungen (NLLB-200).
Lädt das Modell zwingend und deterministisch aus dem lokalen resources-Ordner.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# 🚀 OFFLINE-MODE ERZWINGEN
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

# SYSTEM-PATH FIX
WORKER_ROOT = Path(__file__).resolve().parent.parent
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

PROJECT_ROOT = WORKER_ROOT.parent
LOCAL_MODEL_DIR = PROJECT_ROOT / "resources" / "models" / "nllb"

from common import cleanup_memory, configure_torch_runtime, setup_worker_logging

logger = setup_worker_logging("translation-worker")
configure_torch_runtime()

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer


def _load_lang_map() -> dict:
    map_path = PROJECT_ROOT / "config" / "nllb_mapping.json"
    if map_path.exists():
        try:
            with open(map_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Fehler beim Lesen der nllb_mapping.json: %s", e)
    return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Translation Experte")
    parser.add_argument("--input", required=True, help="Input JSON")
    parser.add_argument("--output", required=True, help="Output JSON")
    parser.add_argument("--lang", required=True, help="Zielsprache (z.B. es)")
    args = parser.parse_args()

    in_file = Path(args.input)
    out_file = Path(args.output)

    with open(in_file, "r", encoding="utf-8") as f:
        texts_to_translate = json.load(f)

    target_iso = args.lang.split("-")[0].lower()
    lang_map = _load_lang_map()
    target_nllb = lang_map.get(target_iso, "eng_Latn")

    if target_nllb == "eng_Latn":
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(texts_to_translate, f, ensure_ascii=False, indent=2)
        sys.exit(0)

    logger.info(
        "🤖 Lade NLLB-200 Translation-Experten lokal aus: %s", LOCAL_MODEL_DIR.name
    )
    device = "cuda" if torch.cuda.is_available() else "cpu"

    if not LOCAL_MODEL_DIR.exists():
        logger.error("❌ Lokales Modell fehlt: %s", LOCAL_MODEL_DIR)
        sys.exit(1)

    model = None
    tokenizer = None

    try:
        # Laden aus exakt dem lokalen Ordner ohne Version-Check
        tokenizer = AutoTokenizer.from_pretrained(
            str(LOCAL_MODEL_DIR), src_lang="eng_Latn", local_files_only=True
        )
        model = AutoModelForSeq2SeqLM.from_pretrained(
            str(LOCAL_MODEL_DIR), local_files_only=True
        ).to(device)

        results = {}
        for key, text in texts_to_translate.items():
            if not text.strip():
                results[key] = ""
                continue

            inputs = tokenizer(text, return_tensors="pt").to(device)
            target_id = tokenizer.convert_tokens_to_ids(target_nllb)

            with torch.no_grad():
                outputs = model.generate(
                    **inputs, forced_bos_token_id=target_id, max_length=100
                )

            results[key] = tokenizer.batch_decode(outputs, skip_special_tokens=True)[0]

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error("❌ Fataler Fehler im Translation-Worker: %s", e)
        sys.exit(1)
    finally:
        del model
        del tokenizer
        cleanup_memory(aggressive=True)


if __name__ == "__main__":
    main()
