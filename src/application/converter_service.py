# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Application Layer.
Kapselt den Konvertierungs-Workflow in einer Pipeline und stellt
eine Facade (ConverterService) für UI-Controller bereit.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.engine import extract_to_spatial
from src.generator import generate_pdf_from_spatial
from src.validation import check_verapdf, get_verapdf_version

logger = logging.getLogger("pdf-converter")


@dataclass
class ConversionResult:
    """DTO für das Endergebnis einer Konvertierung."""

    success: bool
    output_path: Optional[Path] = None
    error_message: Optional[str] = None


class ConversionPipeline:
    """Kapselt die serielle Abfolge der Konvertierungsschritte."""

    def execute(self, input_pdf: Path, output_pdf: Path) -> ConversionResult:
        """Führt Extraktion und Generierung durch."""
        try:
            # 1. Extraction Phase (liefert nun sauber ein DTO)
            extraction = extract_to_spatial(str(input_pdf))

            # 2. Generation Phase
            success = generate_pdf_from_spatial(
                spatial_dom=extraction.spatial_dom,
                input_pdf_path=str(input_pdf),
                images_dict=extraction.images_dict,
                output_path=str(output_pdf),
                original_docinfo=extraction.original_meta,
                doc_lang=extraction.doc_lang,
            )

            if success:
                return ConversionResult(success=True, output_path=output_pdf)

            return ConversionResult(
                success=False,
                error_message="Generator meldet Fehlschlag ohne Exception.",
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("❌ Fehler in der Conversion Pipeline: %s", e)
            return ConversionResult(success=False, error_message=str(e))


class ConverterService:
    """Facade für externe Controller (CLI/GUI)."""

    def __init__(self) -> None:
        self._verapdf_logged = False
        self._pipeline = ConversionPipeline()

    def _log_preflight(self, input_pdf: Path) -> None:
        """Führt Logging und Vorab-Validierung durch."""
        if not self._verapdf_logged:
            logger.info("🛠️ Validierungs-Software: %s", get_verapdf_version())
            self._verapdf_logged = True

        logger.info("🔍 Prüfe Original-PDF (%s)...", input_pdf.name)
        initial_check = check_verapdf(input_pdf, is_final=False)

        if initial_check.get("passed", False):
            logger.info("🟢 Original-PDF ist bereits konform.")
        else:
            logger.info("🔴 Original-PDF ist NICHT barrierefrei.")

    def convert(self, input_pdf: Path, output_pdf: Path) -> ConversionResult:
        """Orchestriert den Konvertierungsprozess."""
        self._log_preflight(input_pdf)
        return self._pipeline.execute(input_pdf, output_pdf)
