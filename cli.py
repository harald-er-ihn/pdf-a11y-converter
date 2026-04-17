#!/usr/bin/env python3
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Kommandozeilen-Interface (CLI) für den PDF A11y Converter.
Schreibt nun einen sauberen Audit-Trail für Systemadministratoren.
"""

import argparse
import json
import logging
import os
import sys
import warnings
from pathlib import Path

os.environ["GIO_USE_VFS"] = "local"
os.environ["GLIB_LOG_LEVEL"] = "4"

from src.config import inject_windows_dlls

inject_windows_dlls()  # MUSS vor dem Import von WeasyPrint ausgeführt werden!

# JIT-Patching der Worker-Umgebungen
from src.infrastructure.runtime.bootstrap import VenvPatcher

VenvPatcher.patch_all_venvs()

from src.application.orchestrator import extract_to_spatial
from src.infrastructure.pdf.generator import generate_pdf_from_spatial
from src.infrastructure.validation.validation import check_verapdf, get_verapdf_version
from src.vsr_generator import generate_physical_vsr

warnings.filterwarnings("ignore", category=UserWarning, module="requests")
warnings.filterwarnings("ignore", message=".*urllib3.*")


def main() -> None:
    """Haupteinstiegspunkt für die Ausführung über die Kommandozeile."""
    parser = argparse.ArgumentParser(
        description="PDF A11y Converter - Experten-Edition (CLI)",
        add_help=False,
    )
    group_info = parser.add_argument_group("Informationen")
    group_info.add_argument("-h", "--help", action="help", default=argparse.SUPPRESS)
    group_info.add_argument("--usage", action="store_true")
    group_info.add_argument("--version", action="version", version="v0.1.0")

    group_args = parser.add_argument_group("Verarbeitung")
    group_args.add_argument("input", nargs="?")
    group_args.add_argument("-o", "--output")

    group_debug = parser.add_argument_group("Debugging")
    group_debug.add_argument("-v", "--verbose", action="store_true")
    group_debug.add_argument("--visualscreenreader", action="store_true")

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

    out_p = Path(args.output) if args.output else Path(args.input)
    if not args.output:
        out_p = out_p.with_name(out_p.stem + "_pdfua.pdf")

    audit_path = out_p.with_suffix(".audit.json")

    logger.info("🚀 Starte CLI Konvertierung für: %s", args.input)
    logger.info("🛠️ Validierungs-Software: %s", get_verapdf_version())

    initial_check = check_verapdf(args.input, is_final=False)

    if initial_check.get("passed", False):
        logger.info("🟢 Original-PDF ist konform. Verarbeite trotzdem...")
    else:
        logger.info("🔴 Original-PDF ist NICHT barrierefrei. Starte Rekonstruktion...")

    sp_dom, imgs, lang, docinfo, audit = extract_to_spatial(args.input)

    generate_pdf_from_spatial(sp_dom, args.input, imgs, str(out_p), docinfo, lang)

    # 🚀 ARCHITEKTUR: Endabnahme auf höchster Schicht
    final_check = check_verapdf(out_p, is_final=True)
    audit["validation"] = final_check
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False)

    logger.info("📊 Audit-Trail geschrieben: %s", audit_path.name)

    if args.visualscreenreader:
        vsr_path = out_p.with_suffix(".visualscreenreader.html")
        logger.info("👁️ Generiere Visual Screenreader aus dem fertigen PDF/UA...")
        if generate_physical_vsr(out_p, vsr_path):
            logger.info("👉 file://%s", vsr_path.absolute())


if __name__ == "__main__":
    main()
