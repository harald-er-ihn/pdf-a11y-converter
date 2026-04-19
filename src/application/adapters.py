# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
Adapter Pattern für den Spatial DOM.
Entkoppelt externe Worker-Strukturen vom internen Datenvertrag und
führt die zwingende Koordinaten-Normalisierung durch.
"""

import logging
from typing import Any, Dict, List, Optional

from src.domain.spatial import SpatialDOM, SpatialElement
from src.domain.coordinates import CoordinateAdapter

logger = logging.getLogger("pdf-converter")


class LayoutAdapter:
    """Kapselt die Normalisierung von Layout-Worker-Outputs."""

    @staticmethod
    def normalize_docling(
        raw_data: Dict[str, Any], coord_sys: str = "top_left_points"
    ) -> SpatialDOM:
        try:
            dom = SpatialDOM.model_validate(raw_data)
            CoordinateAdapter.normalize_dom(dom, coord_sys)
            return dom
        except Exception as e:
            logger.error("❌ Docling-Adapter Validierungsfehler: %s", e)
            raise ValueError("Ungültiges Docling-Format.") from e

    @staticmethod
    def normalize_marker(
        raw_data: Dict[str, Any], coord_sys: str = "top_left_points"
    ) -> SpatialDOM:
        try:
            dom = SpatialDOM.model_validate(raw_data)
            CoordinateAdapter.normalize_dom(dom, coord_sys)
            return dom
        except Exception as e:
            logger.error("❌ Marker-Adapter Validierungsfehler: %s", e)
            raise ValueError("Ungültiges Marker-Format.") from e


class TableAdapter:
    """Kapselt die Tabellen-Extrakte."""

    @staticmethod
    def parse(
        raw_data: Dict[str, Any],
        coord_sys: str = "top_left_points",
        page_heights: Optional[Dict[int, float]] = None,
    ) -> Dict[int, List[SpatialElement]]:
        page_heights = page_heights or {}
        result: Dict[int, List[SpatialElement]] = {}
        for page in raw_data.get("pages", []):
            p_num = page.get("page_num")
            p_height = page.get("height") or page_heights.get(p_num, 842.0)
            elements = [
                SpatialElement.model_validate(e) for e in page.get("elements", [])
            ]
            CoordinateAdapter.normalize_elements(elements, coord_sys, p_height)
            result[p_num] = elements
        return result


class FootnoteAdapter:
    """Kapselt die Fußnoten-Extrakte."""

    @staticmethod
    def parse(
        raw_data: Dict[str, Any],
        coord_sys: str = "top_left_points",
        page_heights: Optional[Dict[int, float]] = None,
    ) -> Dict[int, List[SpatialElement]]:
        page_heights = page_heights or {}
        result: Dict[int, List[SpatialElement]] = {}
        for page in raw_data.get("pages", []):
            p_num = page.get("page_num")
            p_height = page.get("height") or page_heights.get(p_num, 842.0)
            elements = [
                SpatialElement.model_validate(e) for e in page.get("elements", [])
            ]
            CoordinateAdapter.normalize_elements(elements, coord_sys, p_height)
            result[p_num] = elements
        return result


class SignatureAdapter:
    """Kapselt die Signatur-Extrakte."""

    @staticmethod
    def parse(
        raw_data: Dict[str, Any],
        coord_sys: str = "top_left_points",
        page_heights: Optional[Dict[int, float]] = None,
    ) -> Dict[int, List[SpatialElement]]:
        page_heights = page_heights or {}
        result: Dict[int, List[SpatialElement]] = {}
        for page in raw_data.get("pages", []):
            p_num = page.get("page_num")
            p_height = page.get("height") or page_heights.get(p_num, 842.0)
            elements = [
                SpatialElement.model_validate(e) for e in page.get("elements", [])
            ]
            CoordinateAdapter.normalize_elements(elements, coord_sys, p_height)
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
            bbox = field.get("bbox", [0.0, 0.0, 10.0, 10.0])
            elements.append(
                SpatialElement(
                    type="p",
                    text=f"Feld: {name} ({alt_text})",
                    bbox=bbox,
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
    def parse(
        raw_data: Dict[str, Any],
        coord_sys: str = "top_left_points",
        page_heights: Optional[Dict[int, float]] = None,
    ) -> Dict[int, List[SpatialElement]]:
        page_heights = page_heights or {}
        result: Dict[int, List[SpatialElement]] = {}
        for page in raw_data.get("pages", []):
            p_num = page.get("page_num")
            p_height = page.get("height") or page_heights.get(p_num, 842.0)
            elements = []
            for col in page.get("columns", []):
                bbox = col.get("bbox", [0.0, 0.0, 0.0, 0.0])
                idx = col.get("column_index", 0)
                elements.append(SpatialElement(type="column", bbox=bbox, text=str(idx)))
            CoordinateAdapter.normalize_elements(elements, coord_sys, p_height)
            result[p_num] = elements
        return result


class HeaderFooterAdapter:
    """Kapselt Header/Footer-Extrakte (Artifacts)."""

    @staticmethod
    def parse(
        raw_data: Dict[str, Any],
        coord_sys: str = "top_left_points",
        page_heights: Optional[Dict[int, float]] = None,
    ) -> Dict[int, List[SpatialElement]]:
        page_heights = page_heights or {}
        result: Dict[int, List[SpatialElement]] = {}
        for page in raw_data.get("pages", []):
            p_num = page.get("page_num")
            p_height = page.get("height") or page_heights.get(p_num, 842.0)
            elements = []
            for el in page.get("elements", []):
                elements.append(
                    SpatialElement(
                        type="artifact",
                        bbox=el.get("bbox", [0.0, 0.0, 0.0, 0.0]),
                        text=el.get("artifact_type", "artifact"),
                    )
                )
            CoordinateAdapter.normalize_elements(elements, coord_sys, p_height)
            result[p_num] = elements
        return result


class CaptionAdapter:
    """Kapselt Caption-Extrakte (Beschriftungen)."""

    @staticmethod
    def parse(
        raw_data: Dict[str, Any],
        coord_sys: str = "top_left_points",
        page_heights: Optional[Dict[int, float]] = None,
    ) -> Dict[int, List[SpatialElement]]:
        page_heights = page_heights or {}
        result: Dict[int, List[SpatialElement]] = {}
        for page in raw_data.get("pages", []):
            p_num = page.get("page_num")
            p_height = page.get("height") or page_heights.get(p_num, 842.0)
            elements = []
            for el in page.get("elements", []):
                c_type = el.get("caption_type", "figure")
                elements.append(
                    SpatialElement(
                        type="caption",
                        bbox=el.get("bbox", [0.0, 0.0, 0.0, 0.0]),
                        text=c_type,
                    )
                )
            CoordinateAdapter.normalize_elements(elements, coord_sys, p_height)
            result[p_num] = elements
        return result
