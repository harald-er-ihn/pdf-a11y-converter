# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Isolierter Worker für Formulare.
Extrahiert interaktive Formularfelder (AcroForms) und deren Bounding Boxes.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# 🚀 SYSTEM-PATH FIX für common import
WORKER_ROOT = Path(__file__).resolve().parent.parent
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from common import cleanup_memory, configure_torch_runtime, setup_worker_logging

logger = setup_worker_logging("form-worker")
configure_torch_runtime()

import pikepdf  # pylint: disable=wrong-import-position


def extract_forms(pdf_path: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Sucht nach AcroForm-Feldern im PDF und extrahiert deren Eigenschaften."""
    form_data: Dict[str, List[Dict[str, Any]]] = {"fields": []}

    try:
        with pikepdf.open(str(pdf_path)) as pdf:
            if "/AcroForm" not in pdf.Root:
                logger.info("Keine interaktiven Formulare im PDF gefunden.")
                return form_data

            acro_form = pdf.Root.AcroForm
            if "/Fields" not in acro_form:
                return form_data

            for field in acro_form.Fields:
                ftype = str(field.get("/FT", "Unknown"))
                fname = str(field.get("/T", "Unnamed")).strip("()")
                fvalue = str(field.get("/V", "")).strip("()")
                alt_text = str(field.get("/TU", fname)).strip("()")

                form_data["fields"].append(
                    {
                        "name": fname,
                        "type": ftype,
                        "value": fvalue,
                        "alt_text": alt_text,
                    }
                )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Fehler bei der Formular-Extraktion: %s", e)

    return form_data


def main() -> None:
    """Haupteinstiegspunkt für den Form-Worker."""
    parser = argparse.ArgumentParser(description="Formular Experte (pikepdf)")
    parser.add_argument("--input", required=True, help="Pfad zum Eingabe-PDF")
    parser.add_argument("--output", required=True, help="Pfad zur Ausgabe-JSON")
    args = parser.parse_args()

    input_pdf = Path(args.input)
    output_json = Path(args.output)

    if not input_pdf.exists():
        logger.error("❌ Eingabedatei nicht gefunden: %s", input_pdf)
        sys.exit(1)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    logger.info("🤖 Formular-Worker analysiert %s...", input_pdf.name)

    try:
        extracted_forms = extract_forms(input_pdf)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(extracted_forms, f, ensure_ascii=False, indent=2)

        logger.info("✅ Formular-Extraktion erfolgreich abgeschlossen.")

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("❌ Fataler Fehler im Form-Worker: %s", e)
        sys.exit(1)

    finally:
        # 🚀 ENTERPRISE MEMORY CLEANUP
        cleanup_memory(aggressive=False)


if __name__ == "__main__":
    main()
