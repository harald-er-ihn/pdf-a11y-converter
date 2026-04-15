# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
Adapter Pattern für den Spatial DOM.
Entkoppelt externe Worker-Strukturen vom internen Datenvertrag.
"""

import logging
from typing import Any, Dict, List

from src.domain.spatial import SpatialDOM, SpatialElement

logger = logging.getLogger("pdf-converter")


class LayoutAdapter:
    """Kapselt die Normalisierung von Layout-Worker-Outputs."""

    @staticmethod
    def normalize_docling(raw_data: Dict[str, Any]) -> SpatialDOM:
        """Wandelt Docling-JSON in einen versionierten SpatialDOM um."""
        try:
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


class TableAdapter:
    """Kapselt die Tabellen-Extrakte."""

    @staticmethod
    def parse(raw_data: Dict[str, Any]) -> Dict[int, List[SpatialElement]]:
        result: Dict[int, List[SpatialElement]] = {}
        for page in raw_data.get("pages", []):
            p_num = page.get("page_num")
            elements = [
                SpatialElement.model_validate(e) for e in page.get("elements", [])
            ]
            result[p_num] = elements
        return result


class FootnoteAdapter:
    """Kapselt die Fußnoten-Extrakte."""

    @staticmethod
    def parse(raw_data: Dict[str, Any]) -> Dict[int, List[SpatialElement]]:
        result: Dict[int, List[SpatialElement]] = {}
        for page in raw_data.get("pages", []):
            p_num = page.get("page_num")
            elements = [
                SpatialElement.model_validate(e) for e in page.get("elements", [])
            ]
            result[p_num] = elements
        return result


class SignatureAdapter:
    """Kapselt die Signatur-Extrakte."""

    @staticmethod
    def parse(raw_data: Dict[str, Any]) -> Dict[int, List[SpatialElement]]:
        result: Dict[int, List[SpatialElement]] = {}
        for page in raw_data.get("pages", []):
            p_num = page.get("page_num")
            elements = [
                SpatialElement.model_validate(e) for e in page.get("elements", [])
            ]
            result[p_num] = elements
        return result


class FormAdapter:
    """Kapselt Formular-Extrakte."""

    @staticmethod
    def parse(raw_data: Dict[str, Any]) -> List[SpatialElement]:
        elements: List[SpatialElement] = []
        for field in raw_data.get("fields", []):
            name = field.get("name", "")
            alt_text = field.get("alt_text", "")
            elements.append(
                SpatialElement(
                    type="p",
                    text=f"Feld: {name} ({alt_text})",
                    bbox=[0.0, 0.0, 10.0, 10.0],
                )
            )
        return elements


class FormulaAdapter:
    """Kapselt Formel-Extrakte."""

    @staticmethod
    def parse(raw_data: Dict[str, Any]) -> str:
        return raw_data.get("markdown", "")


class VisionAdapter:
    """Kapselt Vision-Extrakte."""

    @staticmethod
    def parse(raw_data: Dict[str, Any]) -> Dict[str, str]:
        return {
            str(k): str(v) for k, v in raw_data.items() if k not in ("status", "error")
        }


class ColumnAdapter:
    """Kapselt Spalten-Extrakte in SpatialElements zur weiteren DOM-Fusion."""

    @staticmethod
    def parse(raw_data: Dict[str, Any]) -> Dict[int, List[SpatialElement]]:
        result: Dict[int, List[SpatialElement]] = {}
        for page in raw_data.get("pages", []):
            p_num = page.get("page_num")
            elements = []
            for col in page.get("columns", []):
                bbox = col.get("bbox", [0.0, 0.0, 0.0, 0.0])
                idx = col.get("column_index", 0)
                # Speichert den Index sicher als String-Information
                elements.append(SpatialElement(type="column", bbox=bbox, text=str(idx)))
            result[p_num] = elements
        return result
