# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
Isolierter Worker für die Erkennung von Beschriftungen (Captions).
Findet Bild-, Tabellen- und Formelbeschriftungen heuristisch.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict

# Worker-Pfad für common Imports registrieren
WORKER_ROOT = Path(__file__).resolve().parent.parent
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from common import (
    cleanup_memory,
    setup_worker_logging,
    write_error_contract,
)

logger = setup_worker_logging("caption-worker")

import fitz  # pylint: disable=wrong-import-position


def _get_caption_type(text: str) -> str:
    """Klassifiziert den Text als bestimmte Beschriftung."""
    text_clean = text.strip().lower()

    # Regex für Abbildungen (Figure, Fig., Abbildung, Abb.)
    fig_pattern = r"^(figure|fig\.|abbildung|abb\.)\s*\d+"
    if re.match(fig_pattern, text_clean):
        return "figure"

    # Regex für Tabellen (Table, Tabelle, Tab.)
    tab_pattern = r"^(table|tabelle|tab\.)\s*\d+"
    if re.match(tab_pattern, text_clean):
        return "table"

    # Regex für Formeln (Equation, Eq., Gleichung, Gl.)
    eq_pattern = r"^(equation|eq\.|gleichung|gl\.)\s*\d+"
    # Manchmal auch nur (1) oder [1] am Rand
    eq_alt = r"^[\(\[]\d+[\)\]]$"

    if re.match(eq_pattern, text_clean) or re.match(eq_alt, text_clean):
        return "equation"

    return ""


def extract_captions(pdf_path: Path) -> Dict[str, Any]:
    """Extrahiert Beschriftungen aus dem PDF."""
    result: Dict[str, Any] = {"pages": []}

    try:
        with fitz.open(pdf_path) as doc:
            for page_num, page in enumerate(doc, start=1):
                blocks = page.get_text("dict").get("blocks", [])
                elements = []

                for b in blocks:
                    if b.get("type") != 0:  # Nur Textblöcke
                        continue

                    # Textinhalt zusammensetzen
                    text = "".join(
                        s.get("text", "")
                        for line in b.get("lines", [])
                        for s in line.get("spans", [])
                    ).strip()

                    # Text zu lang für normale Caption
                    if not text or len(text) > 150:
                        continue

                    caption_type = _get_caption_type(text)
                    if caption_type:
                        elements.append(
                            {
                                "type": "caption",
                                "bbox": list(b["bbox"]),
                                "caption_type": caption_type,
                            }
                        )

                if elements:
                    result["pages"].append(
                        {
                            "page_num": page_num,
                            "elements": elements,
                        }
                    )

    except Exception as e:
        logger.error("Fehler bei Caption-Erkennung: %s", e)
        raise

    return result


def main() -> None:
    """Haupteinstiegspunkt für den Caption-Worker."""
    parser = argparse.ArgumentParser(description="Caption Experte")
    parser.add_argument("--input", required=True, help="Pfad zum PDF")
    parser.add_argument("--output", required=True, help="Ausgabe-JSON")
    args = parser.parse_args()

    input_pdf = Path(args.input)
    output_json = Path(args.output)

    if not input_pdf.exists():
        logger.error("❌ Eingabedatei nicht gefunden: %s", input_pdf)
        sys.exit(1)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    logger.info("🤖 Caption-Worker analysiert %s...", input_pdf.name)

    try:
        extracted = extract_captions(input_pdf)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(extracted, f, ensure_ascii=False, indent=2)

        elem_count = sum(len(p.get("elements", [])) for p in extracted.get("pages", []))
        logger.info("✅ %s Captions erfolgreich identifiziert.", elem_count)

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("❌ Fataler Fehler im Caption-Worker: %s", e)
        write_error_contract(output_json, type(e).__name__, str(e))
        sys.exit(1)

    finally:
        cleanup_memory(aggressive=False)


if __name__ == "__main__":
    main()
