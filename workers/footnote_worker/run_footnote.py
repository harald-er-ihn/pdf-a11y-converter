# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Isolierter Worker für Fußnoten.
100% lokaler, heuristischer Ansatz via PyMuPDF (fitz).
Benötigt keinen externen GROBID-Server und keine Docker-Container!
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict

# 🚀 SYSTEM-PATH FIX für common import
WORKER_ROOT = Path(__file__).resolve().parent.parent
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from common import cleanup_memory, configure_torch_runtime, setup_worker_logging

logger = setup_worker_logging("footnote-worker")
configure_torch_runtime()

import fitz  # pylint: disable=wrong-import-position


def _get_page_median_font_size(page: fitz.Page) -> float:
    """Ermittelt die Standard-Schriftgröße des Fließtextes auf der Seite."""
    sizes = []
    blocks = page.get_text("dict", sort=False).get("blocks", [])
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if text:
                    sizes.append(span.get("size", 10.0))
    if not sizes:
        return 10.0
    sizes.sort()
    return sizes[len(sizes) // 2]


def extract_footnotes_local(pdf_path: Path) -> Dict[str, Any]:
    """
    Sucht lokal nach Fußnoten.
    Regeln:
    1. Steht im unteren Bereich der Seite (y > 65%).
    2. Schriftgröße ist meist kleiner als der Fließtext.
    3. Beginnt typischerweise mit einer Zahl oder einem Symbol (1., [1], *, †).
    """
    spatial_data: Dict[str, Any] = {"pages": []}

    # Regex für typische Fußnoten-Marker: "1. ", "[1] ", "* ", "1) "
    footnote_pattern = re.compile(r"^(\d+[\.\)]|\[\d+\]|[\*\†\‡\§])\s")

    try:
        with fitz.open(pdf_path) as doc:
            for page_num, page in enumerate(doc, start=1):
                page_height = page.rect.height
                median_size = _get_page_median_font_size(page)
                elements = []

                blocks = page.get_text("dict", sort=True).get("blocks", [])
                for block in blocks:
                    if block.get("type") != 0:  # Nur Textblöcke
                        continue

                    bbox = block["bbox"]
                    # Regel 1: Unteres Drittel/Viertel der Seite
                    if bbox[1] < page_height * 0.65:
                        continue

                    # Text und durchschnittliche Größe des Blocks sammeln
                    block_text = ""
                    block_sizes = []
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            txt = span.get("text", "")
                            if txt.strip():
                                block_text += txt + " "
                                block_sizes.append(span.get("size", 10.0))

                    block_text = block_text.strip()
                    if not block_text:
                        continue

                    avg_size = sum(block_sizes) / len(block_sizes)

                    # Regel 2 & 3: Kleinere Schrift ODER passendes Prefix-Muster
                    is_smaller = avg_size < (median_size * 0.95)
                    matches_pattern = bool(footnote_pattern.match(block_text))

                    # Wenn es wie eine Fußnote aussieht, markieren wir es!
                    if matches_pattern or (is_smaller and len(block_text) > 5):
                        elements.append(
                            {
                                "page_num": page_num,
                                "type": "Note",
                                "bbox": list(bbox),
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
        logger.error("Fehler bei der lokalen Fußnoten-Extraktion: %s", e)
        raise

    return spatial_data


def main() -> None:
    """Haupteinstiegspunkt für den lokalen Footnote-Worker."""
    parser = argparse.ArgumentParser(description="Fußnoten Experte (Local/PyMuPDF)")
    parser.add_argument("--input", required=True, help="Pfad zum Eingabe-PDF")
    parser.add_argument("--output", required=True, help="Pfad zur Ausgabe-JSON")
    args = parser.parse_args()

    input_pdf = Path(args.input)
    output_json = Path(args.output)

    if not input_pdf.exists():
        logger.error("❌ Eingabedatei nicht gefunden: %s", input_pdf)
        sys.exit(1)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    logger.info("🤖 Footnote-Worker analysiert %s (lokal)...", input_pdf.name)

    try:
        extracted = extract_footnotes_local(input_pdf)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(extracted, f, ensure_ascii=False, indent=2)

        note_count = sum(len(p.get("elements", [])) for p in extracted.get("pages", []))
        logger.info("✅ %s Fußnote(n) lokal extrahiert.", note_count)

    except Exception as e:
        logger.error("❌ Fataler Fehler im Footnote-Worker: %s", e)
        sys.exit(1)

    finally:
        cleanup_memory(aggressive=False)


if __name__ == "__main__":
    main()
