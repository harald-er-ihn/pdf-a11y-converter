# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Isolierter Worker für Tabellen.
Garantiert 100% rechteckige Tabellen und füllt leere Header-Zellen
sprachabhängig (i18n) auf, um PAC26 Fehler restlos zu beheben.
"""

import argparse
import html
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List

import pdfplumber

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S"
)
logger = logging.getLogger("table-worker")


def get_column_word(lang_code: str) -> str:
    """Gibt das lokalisierte Wort für 'Spalte' zurück (i18n)."""
    base_lang = lang_code.split("-")[0].lower()
    translations = {
        "de": "Spalte",
        "en": "Column",
        "es": "Columna",
        "fr": "Colonne",
        "it": "Colonna",
        "nl": "Kolom",
        "pt": "Coluna",
        "pl": "Kolumna",
    }
    return translations.get(base_lang, "Column")


# pylint: disable=too-many-nested-blocks
def extract_spatial_tables(pdf_path: Path, doc_lang: str) -> Dict[str, Any]:
    """Extrahiert Tabellen streng nach PAC26 Table-Regularity Regeln."""
    spatial_data: Dict[str, Any] = {"pages": []}
    col_word = get_column_word(doc_lang)

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                tables = page.find_tables()
                page_elements: List[Dict[str, Any]] = []

                for table in tables:
                    data = table.extract()
                    if not data:
                        continue

                    # 1. PAC26 Fix: Maximale Spaltenzahl ermitteln
                    max_cols = max((len(r) for r in data), default=1)

                    bbox = [table.bbox[0], table.bbox[1], table.bbox[2], table.bbox[3]]

                    html_table = "<table style='width:100%; height:100%;'>\n"

                    for row_idx, row in enumerate(data):
                        html_table += "<tr>\n"

                        padded_row = list(row)
                        while len(padded_row) < max_cols:
                            padded_row.append("")

                        for col_idx, cell in enumerate(padded_row):
                            c_txt = str(cell).replace("\n", " ") if cell else ""
                            c_txt = html.escape(c_txt.strip())

                            if row_idx == 0:
                                # 🚀 PAC26 Fix: Keine leeren TH Tags!
                                if not c_txt:
                                    c_txt = f"{col_word} {col_idx + 1}"
                                html_table += f"<th scope='col'>{c_txt}</th>\n"
                            else:
                                if not c_txt:
                                    c_txt = " "
                                html_table += f"<td>{c_txt}</td>\n"

                        html_table += "</tr>\n"

                    html_table += "</table>"

                    page_elements.append(
                        {"type": "table", "html": html_table, "bbox": bbox}
                    )

                if page_elements:
                    spatial_data["pages"].append(
                        {
                            "page_num": page_num,
                            "width": float(page.width),
                            "height": float(page.height),
                            "elements": page_elements,
                        }
                    )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Fehler bei der Tabellen-Extraktion: %s", e)

    return spatial_data


def main() -> None:
    """Haupteinstiegspunkt für den Table-Worker."""
    parser = argparse.ArgumentParser(description="Tabellen Experte")
    parser.add_argument("--input", required=True, help="Pfad zum PDF")
    parser.add_argument("--output", required=True, help="Ausgabe-JSON")
    parser.add_argument("--lang", default="de-DE", help="Dokumentensprache")
    args = parser.parse_args()

    input_pdf = Path(args.input)
    output_json = Path(args.output)

    if not input_pdf.exists():
        logger.error("❌ Eingabedatei nicht gefunden: %s", input_pdf)
        sys.exit(1)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    logger.info("🤖 Table-Worker analysiert %s...", input_pdf.name)

    # 🚀 FIX: args.lang wird jetzt sauber übergeben!
    extracted = extract_spatial_tables(input_pdf, args.lang)

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(extracted, f, ensure_ascii=False, indent=2)

    table_count = sum(len(p.get("elements", [])) for p in extracted.get("pages", []))
    logger.info("✅ %s Tabelle(n) erfolgreich extrahiert.", table_count)


if __name__ == "__main__":
    main()
