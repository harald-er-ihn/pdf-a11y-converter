#!/usr/bin/env python3
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Markdown zu PDF Konverter für Testzwecke (Portable Edition).
Nutzt eine lokale Pandoc & Tectonic (Rust-basierte TeX-Engine) Installation,
um das OS nicht mit gigantischen TeX-Paketen zuzumüllen.
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S"
)
logger = logging.getLogger("md-to-pdf")


def get_project_root() -> Path:
    """Ermittelt den Hauptordner des Projekts."""
    return Path(__file__).resolve().parent.parent


def md_to_pdf(md_path: Path, pdf_path: Path) -> bool:
    """Konvertiert Markdown zu PDF mit den portablen Binaries."""
    if not md_path.exists():
        logger.error("❌ Eingabedatei nicht gefunden: %s", md_path)
        return False

    base_dir = get_project_root()
    pandoc_bin = base_dir / "tools" / "bin" / "pandoc"
    tectonic_bin = base_dir / "tools" / "bin" / "tectonic"

    if not pandoc_bin.exists() or not tectonic_bin.exists():
        logger.error("❌ Portable Binaries (Pandoc/Tectonic) fehlen!")
        logger.info("💡 Bitte lade sie wie in Schritt 1 beschrieben herunter.")
        return False

    logger.info("🔄 Konvertiere %s nach PDF (via Tectonic)...", md_path.name)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    # Der Befehl nutzt explizit unsere Tools aus der großen SSD
    cmd = [
        str(pandoc_bin),
        str(md_path),
        "-o",
        str(pdf_path),
        f"--pdf-engine={tectonic_bin}",
        "-V",
        "geometry:margin=2.5cm",
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info("✅ Erfolgreich erstellt: %s", pdf_path)
        return True

    except subprocess.CalledProcessError as e:
        logger.error("❌ Fehler bei der Konvertierung (Exit Code %s)!", e.returncode)
        # BUGFIX: Fehler-Output auf ERROR statt DEBUG setzen, damit er immer sichtbar ist!
        logger.error("🔴 GRUND (Pandoc/Tectonic Error):\n%s", e.stderr.strip())
        return False
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("❌ Unerwarteter System-Fehler beim Aufruf der Tools:")
        logger.error(str(e))
        return False


def main() -> None:
    """Haupteinstiegspunkt für das CLI-Tool."""
    parser = argparse.ArgumentParser(
        description="MD zu PDF Konverter (Portable Tectonic Edition)"
    )
    parser.add_argument("input", type=str, help="Pfad zur Eingabe-Markdown-Datei (.md)")
    parser.add_argument(
        "-o", "--output", type=str, help="Pfad zur Ausgabe-PDF (optional)"
    )

    args = parser.parse_args()
    input_path = Path(args.input)

    output_path = Path(args.output) if args.output else input_path.with_suffix(".pdf")

    success = md_to_pdf(input_path, output_path)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
