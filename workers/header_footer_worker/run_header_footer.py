# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
Isolierter Worker für Header und Footer (Artifacts).
Erkennt Seitenzahlen, Running Headers und marginale Texte,
um mehrfaches Vorlesen durch Screenreader zu verhindern.
"""

import argparse
import json
import re
import sys
from collections import Counter
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

logger = setup_worker_logging("header-footer-worker")

import fitz  # pylint: disable=wrong-import-position


def _is_page_number(text: str) -> bool:
    """Prüft mittels Regex, ob ein Text eine Seitenzahl ist."""
    val = text.strip().lower()
    pattern = r"^(\d+|page \d+|seite \d+|\d+/\d+)$"
    return bool(re.match(pattern, val))


def extract_header_footer(pdf_path: Path) -> Dict[str, Any]:
    """Erkennt Header und Footer über Bounding Boxes und Häufigkeit."""
    result: Dict[str, Any] = {"pages":[]}
    text_freq: Counter = Counter()
    pages_data =[]

    try:
        with fitz.open(pdf_path) as doc:
            total_pages = len(doc)

            # Pass 1: Frequenzanalyse für marginale Texte
            for page in doc:
                ph = page.rect.height
                blocks = page.get_text("dict").get("blocks", [])
                page_blocks =[]

                for b in blocks:
                    if b.get("type") != 0:  # Nur Textblöcke
                        continue

                    # Textinhalt des gesamten Blocks zusammensetzen
                    text = "".join(
                        s.get("text", "")
                        for line in b.get("lines", [])
                        for s in line.get("spans",[])
                    ).strip()

                    if not text:
                        continue

                    bbox = b["bbox"]
                    page_blocks.append({"bbox": bbox, "text": text})

                    # Frequenz nur an den Rändern (Top/Bottom 15%) zählen
                    if bbox[3] < ph * 0.15 or bbox[1] > ph * 0.85:
                        text_freq[text] += 1

                pages_data.append({"height": ph, "blocks": page_blocks})

            # Pass 2: Klassifizierung in Header/Footer
            for p_num, p_data in enumerate(pages_data, start=1):
                ph = p_data["height"]
                elements =[]

                for b in p_data["blocks"]:
                    text = b["text"]
                    bbox = b["bbox"]
                    y0, y1 = bbox[1], bbox[3]

                    is_top = y1 < ph * 0.10
                    is_bottom = y0 > ph * 0.90

                    # Häufigkeit (taucht auf > 20% der Seiten auf)
                    is_freq = text_freq[text] > max(2.0, total_pages * 0.20)
                    is_num = _is_page_number(text)

                    artifact_type = ""

                    if is_top:
                        artifact_type = "header"
                    elif is_bottom:
                        artifact_type = "footer"
                    elif is_num and y1 < ph * 0.15:
                        artifact_type = "header"
                    elif is_num and y0 > ph * 0.85:
                        artifact_type = "footer"
                    elif is_freq and y1 < ph * 0.15:
                        artifact_type = "header"
                    elif is_freq and y0 > ph * 0.85:
                        artifact_type = "footer"

                    if artifact_type:
                        elements.append(
                            {
                                "type": "artifact",
                                "bbox": list(bbox),
                                "artifact_type": artifact_type,
                            }
                        )

                if elements:
                    result["pages"].append(
                        {
                            "page_num": p_num,
                            "elements": elements,
                        }
                    )

    except Exception as e:
        logger.error("Fehler bei Header/Footer Erkennung: %s", e)
        raise

    return result


def main() -> None:
    """Haupteinstiegspunkt für den Header/Footer-Worker."""
    parser = argparse.ArgumentParser(description="Header/Footer Experte")
    parser.add_argument("--input", required=True, help="Pfad zum PDF")
    parser.add_argument("--output", required=True, help="Ausgabe-JSON")
    args = parser.parse_args()

    input_pdf = Path(args.input)
    output_json = Path(args.output)

    if not input_pdf.exists():
        logger.error("❌ Eingabedatei nicht gefunden: %s", input_pdf)
        sys.exit(1)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    logger.info("🤖 Header/Footer-Worker analysiert %s...", input_pdf.name)

    try:
        extracted = extract_header_footer(input_pdf)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(extracted, f, ensure_ascii=False, indent=2)

        elem_count = sum(
            len(p.get("elements", [])) for p in extracted.get("pages",[])
        )
        logger.info("✅ %s Artifacts erfolgreich identifiziert.", elem_count)

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("❌ Fataler Fehler im Header/Footer-Worker: %s", e)
        write_error_contract(output_json, type(e).__name__, str(e))
        sys.exit(1)

    finally:
        cleanup_memory(aggressive=False)


if __name__ == "__main__":
    main()
