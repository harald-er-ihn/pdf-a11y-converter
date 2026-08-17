#!/usr/bin/env python3
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Kommandozeilen-Tool zur Generierung des Visual Screenreaders.
Nutzt das DRY Pattern und ruft die physische PDF-Analyse aus dem Core auf.
"""

import argparse
import sys
from pathlib import Path

# Passe den Pfad an, damit src/ gefunden wird, wenn aus tools/ aufgerufen
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pylint: disable=wrong-import-position
from src.vsr_generator import generate_physical_vsr
from src.infrastructure.pdf.tag_extractor import extract_existing_tags


def main() -> None:
    """Fassade für das CLI-Tool."""
    parser = argparse.ArgumentParser(
        description="Generiert den PAC26 HTML-Screenreader aus echten PDF-Tags."
    )
    parser.add_argument("input", help="Pfad zur PDF-Datei")
    parser.add_argument(
        "--tags-json",
        action="store_true",
        help="Extrahiert zusätzlich vorhandene PDF-Tags als JSON-Artefakt.",
    )
    parser.add_argument(
        "--tags-output",
        help=(
            "Pfad für das JSON-Tag-Artefakt. "
            "Default: <input>.existing_tags.json"
        ),
    )
    args = parser.parse_args()

    pdf_path = Path(args.input)
    if not pdf_path.exists():
        print(f"❌ Datei nicht gefunden: {pdf_path}")
        sys.exit(1)

    out_path = pdf_path.with_suffix(".visualscreenreader.html")

    if args.tags_json:
        tags_path = (
            Path(args.tags_output)
            if args.tags_output
            else pdf_path.with_suffix(".existing_tags.json")
        )
        print(f"🏷️ Extrahiere vorhandene PDF-Tags nach {tags_path}...")
        tag_result = extract_existing_tags(pdf_path, tags_path)
        summary = tag_result.get("summary", {})
        print(
            "   "
            f"status={tag_result.get('status')} "
            f"is_tagged={tag_result.get('is_tagged')} "
            f"tags={summary.get('tag_count', 0)} "
            f"mcids={summary.get('mcid_count', 0)} "
            f"alt={summary.get('alt_count', 0)} "
            f"actual_text={summary.get('actual_text_count', 0)}"
        )

    print(f"📄 Analysiere physischen Tag-Baum von {pdf_path.name}...")

    success = generate_physical_vsr(pdf_path, out_path)

    if success:
        print("✅ Visual Screenreader (HTML) erfolgreich erstellt:")
        print(f"👉 file://{out_path.absolute()}")
    else:
        print("❌ Das PDF enthält keine sauberen Tags (StructTreeRoot fehlt).")
        sys.exit(1)


if __name__ == "__main__":
    main()
