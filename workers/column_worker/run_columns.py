# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
Isolierter Worker für die Spaltenerkennung (Column Detection).
Nutzt eine X-Histogramm Heuristik über PyMuPDF-Textblöcke.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Worker-Pfad für common Imports
WORKER_ROOT = Path(__file__).resolve().parent.parent
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from common import (
    cleanup_memory,
    setup_worker_logging,
    write_error_contract,
)

logger = setup_worker_logging("column-worker")

import fitz  # pylint: disable=wrong-import-position


def _build_x_histogram(
    blocks: List[List[float]], page_width: float
) -> List[Tuple[int, int]]:
    """Baut ein Histogramm der X-Achse zur Spaltenfindung."""
    width_int = int(page_width + 1)
    hist = [0] * width_int

    for b in blocks:
        x0, x1 = int(max(0, b[0])), int(min(page_width, b[2]))
        for x in range(x0, x1):
            hist[x] += 1

    ranges = []
    in_col = False
    start = 0

    # Schwellenwert für Lücken (z.B. 15 Punkte = ca. 5mm Abstand)
    gap_threshold = 15
    gap_count = 0

    for x in range(width_int):
        val = hist[x]
        if val > 0:
            if not in_col:
                start = x
                in_col = True
            gap_count = 0
        else:
            if in_col:
                gap_count += 1
                if gap_count > gap_threshold:
                    ranges.append((start, x - gap_count))
                    in_col = False
                    gap_count = 0

    if in_col:
        ranges.append((start, width_int))

    return ranges


def extract_columns(pdf_path: Path) -> Dict[str, Any]:
    """Extrahiert die Spalten-Bounding-Boxes pro Seite."""
    result: Dict[str, Any] = {"pages": []}

    with fitz.open(pdf_path) as doc:
        for page_num, page in enumerate(doc, start=1):
            pw = page.rect.width
            ph = page.rect.height

            # Alle echten Textblöcke holen
            raw_blocks = page.get_text("blocks")
            valid_blocks = []

            for b in raw_blocks:
                if b[6] != 0:  # Typ 0 = Text
                    continue
                if not b[4].strip():
                    continue
                # Ignoriere volle Seitenbreite (Kopf-/Fußzeilen / Titel)
                if (b[2] - b[0]) > 0.85 * pw:
                    continue
                valid_blocks.append([b[0], b[1], b[2], b[3]])

            if not valid_blocks:
                # Fallback: Eine Spalte für die ganze Seite
                result["pages"].append(
                    {
                        "page_num": page_num,
                        "columns": [
                            {
                                "bbox": [0.0, 0.0, pw, ph],
                                "column_index": 0,
                            }
                        ],
                    }
                )
                continue

            col_ranges = _build_x_histogram(valid_blocks, pw)
            columns_data = []

            for col_idx, (cx0, cx1) in enumerate(col_ranges):
                # Finde alle Blöcke, die in diese Spalte fallen
                col_blocks = [
                    b
                    for b in valid_blocks
                    if (b[0] + b[2]) / 2 >= cx0 and (b[0] + b[2]) / 2 <= cx1
                ]

                if not col_blocks:
                    continue

                # Bounding Box der gesamten Spalte berechnen
                min_x = min(b[0] for b in col_blocks)
                min_y = min(b[1] for b in col_blocks)
                max_x = max(b[2] for b in col_blocks)
                max_y = max(b[3] for b in col_blocks)

                columns_data.append(
                    {
                        "bbox": [min_x, min_y, max_x, max_y],
                        "column_index": col_idx,
                    }
                )

            # Fallback, falls die Heuristik komplett fehlschlägt
            if not columns_data:
                columns_data.append(
                    {
                        "bbox": [0.0, 0.0, pw, ph],
                        "column_index": 0,
                    }
                )

            result["pages"].append(
                {
                    "page_num": page_num,
                    "columns": columns_data,
                }
            )

    return result


def main() -> None:
    """Haupteinstiegspunkt für den Column-Worker."""
    parser = argparse.ArgumentParser(description="Column Experte")
    parser.add_argument("--input", required=True, help="Pfad zum PDF")
    parser.add_argument("--output", required=True, help="Ausgabe-JSON")
    args = parser.parse_args()

    input_pdf = Path(args.input)
    output_json = Path(args.output)

    if not input_pdf.exists():
        logger.error("❌ Eingabedatei nicht gefunden: %s", input_pdf)
        sys.exit(1)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    logger.info("🤖 Column-Worker analysiert %s...", input_pdf.name)

    try:
        extracted = extract_columns(input_pdf)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(extracted, f, ensure_ascii=False, indent=2)

        col_count = sum(len(p.get("columns", [])) for p in extracted.get("pages", []))
        logger.info("✅ %s Spalte(n) erfolgreich extrahiert.", col_count)

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("❌ Fataler Fehler im Column-Worker: %s", e)
        write_error_contract(output_json, type(e).__name__, str(e))
        sys.exit(1)

    finally:
        cleanup_memory(aggressive=False)


if __name__ == "__main__":
    main()
