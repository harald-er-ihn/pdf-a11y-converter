# workers/table_worker/run_tables.py
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Isolierter Worker für Tabellen.
Garantiert 100% rechteckige Tabellen und füllt leere Header-Zellen
sprachabhängig (i18n) auf, um PAC26 Fehler restlos zu beheben.
Nutzt robuste Toleranzen, um Fließtexte nicht als Tabellen zu halluzinieren.
"""

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# 🚀 SYSTEM-PATH FIX für common import
WORKER_ROOT = Path(__file__).resolve().parent.parent
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from common import cleanup_memory, configure_torch_runtime, setup_worker_logging

logger = setup_worker_logging("table-worker")
configure_torch_runtime()

import pdfplumber  # pylint: disable=wrong-import-position


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
    spatial_data: Dict[str, Any] = {"pages": list()}
    col_word = get_column_word(doc_lang)

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                # 🚀 ARCHITEKTUR-FIX: Hohe Toleranzen verhindern, dass Abstände
                # zwischen Wörtern im Blocksatz als Tabellenspalten halluziniert werden!
                tables = page.find_tables(
                    {
                        "vertical_strategy": "text",
                        "horizontal_strategy": "text",
                        "intersection_x_tolerance": 25,
                        "intersection_y_tolerance": 25,
                    }
                )
                page_elements: List[Dict[str, Any]] = list()

                for table in tables:
                    data = table.extract()
                    if not data:
                        continue

                    # Grid-Validation: Eine Tabelle muss ein Grid sein (2x2)
                    max_cols = max((len(r) for r in data), default=0)
                    max_rows = len(data)
                    if max_cols < 2 or max_rows < 2:
                        continue

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

    try:
        extracted = extract_spatial_tables(input_pdf, args.lang)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(extracted, f, ensure_ascii=False, indent=2)

        table_count = 0
        pages_data = extracted.get("pages")
        if pages_data is not None:
            for p_data in pages_data:
                elements_data = p_data.get("elements")
                if elements_data is not None:
                    table_count += len(elements_data)

        logger.info("✅ %s Tabelle(n) erfolgreich extrahiert.", table_count)

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("❌ Fataler Fehler im Table-Worker: %s", e)
        sys.exit(1)

    finally:
        cleanup_memory(aggressive=False)


if __name__ == "__main__":
    main()
