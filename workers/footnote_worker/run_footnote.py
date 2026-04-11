# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Isolierter Worker für Fußnoten und Zitationen (GROBID).
Nutzt eine lokale GROBID-Instanz, um die exakten Koordinaten (Bounding Boxes)
von Fußnoten im Dokument zu identifizieren.
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict

# 🚀 SYSTEM-PATH FIX für common import
WORKER_ROOT = Path(__file__).resolve().parent.parent
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from common import cleanup_memory, configure_torch_runtime, setup_worker_logging

logger = setup_worker_logging("footnote-worker")
configure_torch_runtime()

import requests  # pylint: disable=wrong-import-position

GROBID_URL = "http://localhost:8070/api/processFulltextDocument"


def _parse_grobid_coords(coords_str: str) -> list[dict[str, Any]]:
    """Hilfsfunktion zum Parsen der GROBID-Koordinaten-Strings."""
    elements = []
    # GROBID-Koordinaten-Format: "page_num,x,y,width,height;page_num,x,y..."
    for coord in coords_str.split(";"):
        parts = coord.split(",")
        if len(parts) >= 5:
            try:
                page_num = int(parts[0])
                x = float(parts[1])
                y = float(parts[2])
                w = float(parts[3])
                h = float(parts[4])

                # Umrechnung in Standard-BBox[left, top, right, bottom]
                bbox = [x, y, x + w, y + h]
                elements.append({"page_num": page_num, "type": "Note", "bbox": bbox})
            except ValueError:
                continue
    return elements


def extract_footnotes_via_grobid(pdf_path: Path) -> Dict[str, Any]:
    """
    Sendet das PDF an GROBID und parst die zurückgegebenen TEI XML-Koordinaten.
    Fail-Fast: Ist GROBID offline, wird ein leeres Ergebnis zurückgegeben.
    """
    spatial_data: Dict[str, Any] = {"pages": []}
    pages_dict: Dict[int, list[dict[str, Any]]] = {}

    try:
        with open(pdf_path, "rb") as f:
            # Wir fordern explizit die Koordinaten für "note" (Fußnoten) an
            files = {"input": (pdf_path.name, f, "application/pdf")}
            data = {"teiCoordinates": ["note"]}

            response = requests.post(GROBID_URL, files=files, data=data, timeout=60)

        if response.status_code != 200:
            logger.warning("⚠️ GROBID API Fehler: Status %s", response.status_code)
            return spatial_data

        root = ET.fromstring(response.text)
        ns = {"tei": "http://www.tei-c.org/ns/1.0"}
        notes = root.findall(".//tei:note[@place='foot']", ns)

        for note in notes:
            coords_str = note.attrib.get("coords")
            if not coords_str:
                continue

            parsed_elements = _parse_grobid_coords(coords_str)
            for el in parsed_elements:
                p_num = el.pop("page_num")
                if p_num not in pages_dict:
                    pages_dict[p_num] = []
                pages_dict[p_num].append(el)

        for p_num, elements in pages_dict.items():
            spatial_data["pages"].append(
                {
                    "page_num": p_num,
                    "elements": elements,
                }
            )

    except requests.exceptions.RequestException as e:
        logger.warning("⚠️ GROBID nicht erreichbar (%s). Überspringe Fußnoten.", e)
    except ET.ParseError as e:
        logger.error("❌ Fehler beim Parsen der GROBID TEI XML-Antwort: %s", e)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("❌ Unerwarteter Fehler bei der Fußnoten-Extraktion: %s", e)

    return spatial_data


def main() -> None:
    """Haupteinstiegspunkt für den Footnote-Worker."""
    parser = argparse.ArgumentParser(description="Fußnoten Experte (GROBID)")
    parser.add_argument("--input", required=True, help="Pfad zum Eingabe-PDF")
    parser.add_argument("--output", required=True, help="Pfad zur Ausgabe-JSON")
    args = parser.parse_args()

    input_pdf = Path(args.input)
    output_json = Path(args.output)

    if not input_pdf.exists():
        logger.error("❌ Eingabedatei nicht gefunden: %s", input_pdf)
        sys.exit(1)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    logger.info("🤖 Footnote-Worker analysiert %s...", input_pdf.name)

    try:
        extracted = extract_footnotes_via_grobid(input_pdf)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(extracted, f, ensure_ascii=False, indent=2)

        note_count = sum(len(p.get("elements", [])) for p in extracted.get("pages", []))
        logger.info("✅ %s Fußnote(n) erfolgreich extrahiert.", note_count)

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("❌ Fataler Fehler im Footnote-Worker: %s", e)
        sys.exit(1)

    finally:
        # 🚀 ENTERPRISE MEMORY CLEANUP
        cleanup_memory(aggressive=False)


if __name__ == "__main__":
    main()
