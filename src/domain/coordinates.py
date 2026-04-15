# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
Coordinate Adapter Layer.
Normalisiert verschiedene Koordinatensysteme (Pixels, Bottom-Left)
streng in PDF-Standard-Punkte (Top-Left, 72 DPI).
Verhindert stille Mismatches durch Fail-Fast-Design.
"""

import logging
from typing import List

from src.domain.spatial import SpatialDOM, SpatialElement

logger = logging.getLogger("pdf-converter")


class CoordinateAdapter:
    """Anti-Corruption Layer für Koordinatensysteme."""

    @classmethod
    def bottom_left_to_top_left(
        cls, bbox: List[float], page_height: float
    ) -> List[float]:
        """
        Konvertiert Bottom-Left (Standard-PDF) zu Top-Left.
        bbox =[x0, y_bottom, x1, y_top]
        """
        # Neuer y0 (oben) = Höhe - alter y1 (oben)
        # Neuer y1 (unten) = Höhe - alter y0 (unten)
        return [bbox[0], page_height - bbox[3], bbox[2], page_height - bbox[1]]

    @classmethod
    def pixel_to_points(cls, bbox: List[float], dpi: float = 144.0) -> List[float]:
        """Konvertiert Pixel basierend auf der DPI-Auflösung in PDF-Punkte."""
        scale = 72.0 / dpi
        return [x * scale for x in bbox]

    @classmethod
    def convert_to_pdf_points(
        cls, bbox: List[float], system: str, page_height: float, dpi: float = 144.0
    ) -> List[float]:
        """Zentraler Konverter mit Fail-Fast Typsicherheit."""
        if system == "top_left_points":
            return bbox
        elif system == "bottom_left_points":
            return cls.bottom_left_to_top_left(bbox, page_height)
        elif system == "pixel":
            return cls.pixel_to_points(bbox, dpi)
        else:
            logger.error(
                "❌ Kritisches Koordinaten-Mismatch: System '%s' unbekannt.", system
            )
            raise ValueError(f"Unsupported coordinate system declared: {system}")

    @classmethod
    def normalize_dom(cls, dom: SpatialDOM, system: str, dpi: float = 144.0) -> None:
        """Normalisiert einen kompletten SpatialDOM in-place."""
        if system == "top_left_points":
            return

        for page in dom.pages:
            for el in page.elements:
                el.bbox = cls.convert_to_pdf_points(el.bbox, system, page.height, dpi)

    @classmethod
    def normalize_elements(
        cls,
        elements: List[SpatialElement],
        system: str,
        page_height: float,
        dpi: float = 144.0,
    ) -> None:
        """Normalisiert eine Liste von SpatialElements in-place."""
        if system == "top_left_points":
            return

        for el in elements:
            el.bbox = cls.convert_to_pdf_points(el.bbox, system, page_height, dpi)
