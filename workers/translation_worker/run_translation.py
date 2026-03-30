# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Isolierter Worker für KI-Übersetzungen (NLLB-200).
Liest Sprach-Mappings dynamisch aus der config/nllb_mapping.json.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

try:
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
except ImportError:
    print("❌ FEHLER: Module fehlen. Bitte Venv neu bauen:")
    print("   ./tools/rebuild_worker_venvs.sh")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S"
)
logger = logging.getLogger("translation-worker")


def _load_lang_map() -> dict:
    """Lädt die Sprach-Mappings aus der zentralen nllb_mapping.json."""
    base_dir = Path(__file__).resolve().parent.parent.parent
    map_path = base_dir / "config" / "nllb_mapping.json"
    if map_path.exists():
        try:
            with open(map_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Fehler beim Lesen der nllb_mapping.json: %s", e)
    return {}


def main() -> None:
    """Haupteinstiegspunkt für den Übersetzungs-Experten."""
    parser = argparse.ArgumentParser(description="Translation Experte")
    parser.add_argument("--input", required=True, help="Input JSON")
    parser.add_argument("--output", required=True, help="Output JSON")
    parser.add_argument("--lang", required=True, help="Zielsprache (z.B. es)")
    args = parser.parse_args()

    in_file = Path(args.input)
    out_file = Path(args.output)

    if not in_file.exists():
        logger.error("❌ Eingabedatei fehlt: %s", in_file)
        sys.exit(1)

    with open(in_file, "r", encoding="utf-8") as f:
        texts_to_translate = json.load(f)

    target_iso = args.lang.split("-")[0].lower()
    lang_map = _load_lang_map()

    # 🚀 Dynamischer Lookup in der von dir erstellten JSON!
    target_nllb = lang_map.get(target_iso, "eng_Latn")

    if target_nllb == "eng_Latn":
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(texts_to_translate, f, ensure_ascii=False, indent=2)
        logger.info("✅ Ziel ist Englisch. Keine Übersetzung nötig.")
        sys.exit(0)

    logger.info("🤖 Lade NLLB-200 Translation-Experten (%s)...", target_nllb)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model_id = "facebook/nllb-200-distilled-600M"

    try:
        tokenizer = AutoTokenizer.from_pretrained(model_id, src_lang="eng_Latn")
        model = AutoModelForSeq2SeqLM.from_pretrained(model_id).to(device)

        results = {}
        for key, text in texts_to_translate.items():
            if not text.strip():
                results[key] = ""
                continue

            inputs = tokenizer(text, return_tensors="pt").to(device)
            # 🚀 FIX: Kompatibilität für moderne FastTokenizer
            target_id = tokenizer.convert_tokens_to_ids(target_nllb)

            with torch.no_grad():
                outputs = model.generate(
                    **inputs, forced_bos_token_id=target_id, max_length=100
                )

            translated = tokenizer.batch_decode(outputs, skip_special_tokens=True)[0]
            results[key] = translated

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        logger.info("✅ Übersetzung erfolgreich abgeschlossen.")

    except Exception as e:
        logger.error("❌ Fataler Fehler im Translation-Worker: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
