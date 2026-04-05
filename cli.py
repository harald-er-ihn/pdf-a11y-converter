#!/usr/bin/env python3
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Kommandozeilen-Interface (CLI) für den PDF A11y Converter.
Fungiert als reiner Controller, der den ConverterService aufruft.
"""

import argparse
import logging
import os
import sys
import warnings
from pathlib import Path

# 🚀 FIX: Korrekter Import-Pfad (Application Layer)
from src.application.converter_service import ConverterService
from src.vsr_generator import generate_physical_vsr

warnings.filterwarnings("ignore", category=UserWarning, module="requests")
warnings.filterwarnings("ignore", message=".*urllib3.*")


def _parse_args() -> argparse.Namespace:
    """Extrahiert die Argumenten-Logik."""
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
        "--usage", action="store_true", help="Zeigt Verwendungsbeispiel."
    )
    group_info.add_argument(
        "--version", action="version", version="PDF A11y Converter v0.1.0"
    )

    group_args = parser.add_argument_group("Verarbeitung")
    group_args.add_argument("input", nargs="?", help="Pfad zur Eingabe-PDF")
    group_args.add_argument("-o", "--output", help="Pfad zur Ausgabe-PDF")

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
        print("  python cli.py <in.pdf> [-o <out.pdf>] [--visualscreenreader]")
        sys.exit(0)

    if not args.input or not os.path.exists(args.input):
        print(f"\n❌ Fehler: Datei nicht gefunden -> {args.input}\n")
        sys.exit(1)

    return args


def _setup_logger(verbose: bool) -> logging.Logger:
    """Initialisiert das Logging."""
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S"
    )
    return logging.getLogger("pdf-converter")


def main() -> None:
    """Haupteinstiegspunkt für die Kommandozeile."""

    # 🚀 NEU: Enterprise Bootstrap Loader triggern
    from src.runtime_bootstrap import ensure_runtime

    ensure_runtime()

    args = _parse_args()
    logger = _setup_logger(args.verbose)

    in_path = Path(args.input)
    out_path = (
        Path(args.output)
        if args.output
        else in_path.with_name(f"{in_path.stem}_pdfua.pdf")
    )

    logger.info("🚀 Starte CLI Konvertierung für: %s", in_path.name)

    # Facade Pattern: Orchestrierung an Service Layer delegieren
    service = ConverterService()
    result = service.convert(in_path, out_path)

    if not result.success:
        logger.error("🔴 Konvertierung fehlgeschlagen: %s", result.error_message)
        sys.exit(1)

    if args.visualscreenreader:
        vsr_path = (
            Path(args.visualscreenreader)
            if args.visualscreenreader != "DEFAULT"
            else out_path.with_suffix(".visualscreenreader.html")
        )

        logger.info("👁️ Generiere Visual Screenreader...")
        if generate_physical_vsr(out_path, vsr_path):
            logger.info("👉 file://%s", vsr_path.absolute())
        else:
            logger.warning("⚠️ Konnte keinen VSR generieren.")


if __name__ == "__main__":
    main()
