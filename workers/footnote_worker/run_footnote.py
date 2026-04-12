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

from common import (
    cleanup_memory,
    configure_torch_runtime,
    setup_worker_logging,
    write_error_contract,
)

logger = setup_worker_logging("footnote-worker")
configure_torch_runtime()

import requests  # pylint: disable=wrong-import-position

GROBID_URL = "http://localhost:8070/api/processFulltextDocument"


def check_grobid_health() -> bool:
    """Prüft via Health-Check, ob GROBID lokal läuft."""
    try:
        res = requests.get("http://localhost:8070/api/isalive", timeout=2)
        return res.status_code == 200
    except requests.exceptions.RequestException:
        return False


def _parse_grobid_coords(coords_str: str) -> list[dict[str, Any]]:
    """Hilfsfunktion zum Parsen der GROBID-Koordinaten-Strings."""
    elements = []
    for coord in coords_str.split(";"):
        parts = coord.split(",")
        if len(parts) >= 5:
            try:
                page_num = int(parts[0])
                x = float(parts[1])
                y = float(parts[2])
                w = float(parts[3])
                h = float(parts[4])

                bbox = [x, y, x + w, y + h]
                elements.append({"page_num": page_num, "type": "Note", "bbox": bbox})
            except ValueError:
                continue
    return elements


def extract_footnotes_via_grobid(pdf_path: Path) -> Dict[str, Any]:
    """Sendet das PDF an GROBID und parst die zurückgegebenen TEI XML-Koordinaten."""
    spatial_data: Dict[str, Any] = {"pages": []}
    pages_dict: Dict[int, list[dict[str, Any]]] = {}

    with open(pdf_path, "rb") as f:
        files = {"input": (pdf_path.name, f, "application/pdf")}
        data = {"teiCoordinates": ["note"]}
        response = requests.post(GROBID_URL, files=files, data=data, timeout=60)

    if response.status_code != 200:
        raise RuntimeError(f"GROBID API Fehler: Status {response.status_code}")

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

    # 🚀 ENTERPRISE HEALTH-CHECK
    if not check_grobid_health():
        logger.warning("⚠️ GROBID ist offline.")
        write_error_contract(
            output_json,
            "ServiceOffline",
            "Lokaler GROBID-Dienst (Port 8070) antwortet nicht.",
            "Bitte starte den GROBID Docker-Container.",
        )
        sys.exit(1)

    try:
        extracted = extract_footnotes_via_grobid(input_pdf)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(extracted, f, ensure_ascii=False, indent=2)

        note_count = sum(len(p.get("elements", [])) for p in extracted.get("pages", []))
        logger.info("✅ %s Fußnote(n) erfolgreich extrahiert.", note_count)

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("❌ Fataler Fehler im Footnote-Worker: %s", e)
        # 🚀 SCHREIBT DEN ERROR-CONTRACT STATT EINFACH ZU STERBEN
        write_error_contract(output_json, type(e).__name__, str(e))
        sys.exit(1)

    finally:
        cleanup_memory(aggressive=False)


if __name__ == "__main__":
    main()
