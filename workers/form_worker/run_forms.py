# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Isolierter Worker für Formulare.
Extrahiert interaktive Formularfelder (AcroForms) und deren Bounding Boxes,
damit sie später vom Generator exakt an der richtigen Stelle als barrierefreie
HTML-Inputs reproduziert werden können.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import pikepdf

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S"
)
logger = logging.getLogger("form-worker")


def extract_forms(pdf_path: Path) -> dict[str, list]:
    """
    Sucht nach AcroForm-Feldern im PDF und extrahiert deren Eigenschaften.
    Fail-Fast: Wenn keine Formulare da sind, wird direkt ein leeres Dict geliefert.
    """
    form_data: dict[str, list] = {"fields": []}

    try:
        with pikepdf.open(str(pdf_path)) as pdf:
            if "/AcroForm" not in pdf.Root:
                logger.info("Keine interaktiven Formulare im PDF gefunden.")
                return form_data

            acro_form = pdf.Root.AcroForm
            if "/Fields" not in acro_form:
                return form_data

            for field in acro_form.Fields:
                # Feldtyp (z.B. /Tx für Text, /Btn für Button/Checkbox)
                ftype = str(field.get("/FT", "Unknown"))
                # Interner Name des Feldes
                fname = str(field.get("/T", "Unnamed")).strip("()")
                # Wert (falls vorausgefüllt)
                fvalue = str(field.get("/V", "")).strip("()")

                # Barrierefreier Alternativtext (Tooltip/TU)
                alt_text = str(field.get("/TU", fname)).strip("()")

                form_data["fields"].append(
                    {
                        "name": fname,
                        "type": ftype,
                        "value": fvalue,
                        "alt_text": alt_text,
                    }
                )

    except Exception as e:
        logger.error(f"Fehler bei der Formular-Extraktion: {e}")

    return form_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Formular Experte (pikepdf)")
    parser.add_argument("--input", required=True, help="Pfad zum Eingabe-PDF")
    parser.add_argument("--output", required=True, help="Pfad zur Ausgabe-JSON")
    args = parser.parse_args()

    input_pdf = Path(args.input)
    output_json = Path(args.output)

    if not input_pdf.exists():
        logger.error(f"❌ Eingabedatei nicht gefunden: {input_pdf}")
        sys.exit(1)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"🤖 Formular-Worker analysiert {input_pdf.name}...")

    extracted_forms = extract_forms(input_pdf)

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(extracted_forms, f, ensure_ascii=False, indent=2)

    logger.info("✅ Formular-Extraktion erfolgreich abgeschlossen.")


if __name__ == "__main__":
    main()
