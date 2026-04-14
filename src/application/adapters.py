# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Adapter Pattern für den Spatial DOM.
Entkoppelt externe Worker-Strukturen vom internen Datenvertrag.
"""

import logging
from typing import Any, Dict

from src.domain.spatial import SpatialDOM

logger = logging.getLogger("pdf-converter")


class LayoutAdapter:
    """Kapselt die Normalisierung von Layout-Worker-Outputs."""

    @staticmethod
    def normalize_docling(raw_data: Dict[str, Any]) -> SpatialDOM:
        """Wandelt Docling-JSON in einen versionierten SpatialDOM um."""
        try:
            # Hier können künftig Format-Migrationen stattfinden
            return SpatialDOM.model_validate(raw_data)
        except Exception as e:
            logger.error("❌ Docling-Adapter Validierungsfehler: %s", e)
            raise ValueError("Ungültiges Docling-Format.") from e

    @staticmethod
    def normalize_marker(raw_data: Dict[str, Any]) -> SpatialDOM:
        """Wandelt Marker-JSON in einen versionierten SpatialDOM um."""
        try:
            return SpatialDOM.model_validate(raw_data)
        except Exception as e:
            logger.error("❌ Marker-Adapter Validierungsfehler: %s", e)
            raise ValueError("Ungültiges Marker-Format.") from e
