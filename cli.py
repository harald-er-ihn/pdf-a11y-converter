#!/usr/bin/env python3
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Kommandozeilen-Interface (CLI) für den PDF A11y Converter.
"""

import os
import sys
import platform

# 🚀 FIX: GTK3 Runtime + Warnungs-Unterdrückung für Windows
if platform.system().lower() == "windows":
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    gtk3_bin = os.path.join(base_path, "gtk3", "bin")
    if os.path.exists(gtk3_bin):
        os.environ["PATH"] = gtk3_bin + os.pathsep + os.environ.get("PATH", "")
        # Unterdrückt die UWP (Microsoft Outlook/ScreenSketch) Warnungen
        os.environ["GIO_USE_VFS"] = "local"
        os.environ["G_MESSAGES_DEBUG"] = ""
        
        # Behebt den Fontconfig "No such file (null)" Error
        fc_path = os.path.join(base_path, "gtk3", "etc", "fonts")
        os.environ["FONTCONFIG_PATH"] = fc_path
        os.environ["FONTCONFIG_FILE"] = os.path.join(fc_path, "fonts.conf")
        
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(gtk3_bin)

import argparse
import logging
import warnings
from pathlib import Path

from src.engine import extract_to_spatial
from src.generator import generate_pdf_from_spatial
from src.validation import check_verapdf, get_verapdf_version
from src.vsr_generator import generate_physical_vsr

warnings.filterwarnings("ignore", category=UserWarning, module="requests")
warnings.filterwarnings("ignore", message=".*urllib3.*")


def main() -> None:
    """Haupteinstiegspunkt für die Ausführung über die Kommandozeile."""
    parser = argparse.ArgumentParser(
        description="PDF A11y Converter - Experten-Edition (CLI)",
        epilog="Beispiel: python cli.py dokument.pdf -o output.pdf -v",
        add_help=False,
    )

    group_info = parser.add_argument_group("Informationen")
    group_info.add_argument(
        "-h", "--help", action="help", default=argparse.SUPPRESS, help="Zeigt Hilfe an."
    )
    group_info.add_argument(
        "--usage", action="store_true", help="Zeigt ein Verwendungsbeispiel an."
    )
    group_info.add_argument(
        "--version", action="version", version="PDF A11y Converter v0.1.0"
    )

    group_args = parser.add_argument_group("Verarbeitung")
    group_args.add_argument("input", nargs="?", help="Pfad zur Eingabe-PDF")
    group_args.add_argument("-o", "--output", help="Pfad zur Ausgabe-PDF (optional)")

    group_debug = parser.add_argument_group("Debugging")
    group_debug.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose Mode."
    )
    group_debug.add_argument(
        "--visualscreenreader",
        nargs="?",
        const="DEFAULT",
        help="Erzeugt eine textuelle Screenreader-Vorschau (.html)",
    )

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()

    if args.usage:
        print("  python cli.py <eingabe.pdf> [-o <ausgabe.pdf>] [--visualscreenreader]")
        sys.exit(0)

    if not args.input or not os.path.exists(args.input):
        print(f"\n❌ Fehler: Datei nicht gefunden -> {args.input}\n")
        sys.exit(1)

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S"
    )
    logger = logging.getLogger("pdf-converter")

    out_path = (
        Path(args.output)
        if args.output
        else Path(args.input).with_name(Path(args.input).stem + "_pdfua.pdf")
    )
    logger.info("🚀 Starte CLI Konvertierung für: %s", args.input)

    verapdf_v = get_verapdf_version()
    logger.info("🛠️ Validierungs-Software: %s", verapdf_v)

    initial_check = check_verapdf(args.input, is_final=False)

    if initial_check.get("passed", False):
        logger.info(
            "🟢 Fazit: Das Original-PDF ist bereits konform. Verarbeite trotzdem..."
        )
    else:
        logger.info(
            "🔴 Fazit: Das Original-PDF ist NICHT barrierefrei. "
            "Starte Rekonstruktion..."
        )

    spatial_dom, images, doc_lang, docinfo = extract_to_spatial(args.input)

    # Zuerst das PDF rekonstruieren...
    generate_pdf_from_spatial(
        spatial_dom, args.input, images, str(out_path), docinfo, doc_lang
    )

    # ... dann den fertigen Output-Baum als HTML ausgeben
    if args.visualscreenreader:
        vsr_path = (
            Path(args.visualscreenreader)
            if args.visualscreenreader != "DEFAULT"
            else out_path.with_suffix(".visualscreenreader.html")
        )

        logger.info("👁️ Generiere Visual Screenreader aus dem fertigen PDF/UA...")
        success = generate_physical_vsr(out_path, vsr_path)

        if success:
            logger.info("👉 file://%s", vsr_path.absolute())
        else:
            logger.warning("⚠️ Konnte keinen VSR generieren.")


if __name__ == "__main__":
    main()
