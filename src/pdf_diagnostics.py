# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
PDF Preflight Diagnostics.
Analysiert die physische und semantische Struktur eines PDFs vor der
Verarbeitung. Blockiert Formulare durch Tiefenscan der Seiten-Annotationen.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from pypdf import PdfReader

logger = logging.getLogger("pdf-converter")


@dataclass(frozen=True)
class PDFDiagnostics:
    """Immutable Data-Transfer-Object (DTO) für die Analyse-Ergebnisse."""

    is_tagged: bool
    has_type3_fonts: bool
    has_unembedded_fonts: bool
    is_encrypted: bool
    needs_visual_reconstruction: bool
    force_ocr_extraction: bool
    has_forms: bool


class PDFPreflightScanner:
    """Kapselt die Logik zur Analyse der PDF-internen Datenstrukturen."""

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path

    def _check_if_tagged(self, reader: PdfReader) -> bool:
        try:
            root = reader.trailer.get("/Root")
            if root:
                root = root.get_object()
                mark_info = root.get("/MarkInfo")
                if mark_info:
                    mark_info = mark_info.get_object()
                    return bool(mark_info.get("/Marked", False))
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        return False

    def _has_text_layer(self, reader: PdfReader) -> bool:
        """Prüft, ob das PDF echten digitalen Text enthält."""
        text_length = 0
        for i, page in enumerate(reader.pages):
            if i >= 3:
                break
            try:
                text_length += len(page.extract_text() or "")
                if text_length > 50:
                    return True
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        return False

    def _check_if_has_forms(self, reader: PdfReader) -> bool:
        """Prüft auf interaktive Formular-Widgets auf allen Seiten."""
        try:
            # 1. Globaler Check (AcroForm Dictionary)
            root = reader.trailer.get("/Root")
            if root:
                root = root.get_object()
                if "/AcroForm" in root:
                    return True

            # 2. Tiefenscan (Widgets auf Seiten, wichtig für Tectonic/Pandoc)
            for page in reader.pages:
                annots = page.get("/Annots")
                if annots:
                    for annot in annots:
                        obj = annot.get_object()
                        if obj.get("/Subtype") == "/Widget":
                            return True
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        return False

    def _scan_fonts(self, reader: PdfReader) -> Tuple[bool, bool]:
        has_type3 = False
        has_unembedded = False

        for page in reader.pages:
            try:
                res = page.get("/Resources")
                if not res:
                    continue
                res = res.get_object()

                fonts = res.get("/Font")
                if not fonts:
                    continue
                fonts = fonts.get_object()

                for font_key in fonts:
                    f_obj = fonts[font_key].get_object()
                    if f_obj.get("/Subtype") == "/Type3":
                        has_type3 = True
                        continue

                    desc = f_obj.get("/FontDescriptor")
                    if not desc:
                        has_unembedded = True
                    else:
                        desc = desc.get_object()
                        f_keys = ["/FontFile", "/FontFile2", "/FontFile3"]
                        if not any(k in desc for k in f_keys):
                            has_unembedded = True

            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.debug("Fehler beim Font-Scan: %s", e)

        return has_type3, has_unembedded

    def analyze(self) -> PDFDiagnostics:
        """Führt den Scan durch und liefert die Diagnose-Strategie."""
        logger.info("🔍 Führe Preflight-Strukturanalyse durch...")

        try:
            reader = PdfReader(str(self.file_path))
            is_encrypted = reader.is_encrypted
            is_tagged = self._check_if_tagged(reader)
            has_type3, has_unembedded = self._scan_fonts(reader)
            has_text = self._has_text_layer(reader)
            has_forms = self._check_if_has_forms(reader)

            needs_visual = has_type3 or has_unembedded
            force_ocr = not has_text

            return PDFDiagnostics(
                is_tagged=is_tagged,
                has_type3_fonts=has_type3,
                has_unembedded_fonts=has_unembedded,
                is_encrypted=is_encrypted,
                needs_visual_reconstruction=needs_visual,
                force_ocr_extraction=force_ocr,
                has_forms=has_forms,
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("❌ Kritischer Fehler bei PDF-Analyse: %s", e)
            return PDFDiagnostics(
                is_tagged=False,
                has_type3_fonts=True,
                has_unembedded_fonts=True,
                is_encrypted=False,
                needs_visual_reconstruction=True,
                force_ocr_extraction=True,
                has_forms=False,
            )
