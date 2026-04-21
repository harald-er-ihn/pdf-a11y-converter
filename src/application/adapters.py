# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
Adapter Pattern für den Spatial DOM.
Entkoppelt externe Worker-Strukturen vom internen Datenvertrag und
führt die zwingende Koordinaten-Normalisierung durch.
Behebt den Overwrite-Bug: Struktur-Tags erhalten absichtlich text=None.
"""

import logging
from typing import Any, Dict, List, Optional

from src.domain.spatial import SpatialDOM, SpatialElement
from src.domain.coordinates import CoordinateAdapter

logger = logging.getLogger("pdf-converter")


class LayoutAdapter:
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
    @staticmethod
    def parse(
        raw_data: Dict[str, Any],
        coord_sys: str = "bottom_left_points",
        page_heights: Optional[Dict[int, float]] = None,
    ) -> List[SpatialElement]:
        page_heights = page_heights or {}
        p_height = page_heights.get(1, 842.0)
        elements: List[SpatialElement] = []
        for field in raw_data.get("fields", []):
            name = field.get("name", "")
            alt_text = field.get("alt_text", "")
            bbox = field.get("bbox", [0.0, 0.0, 10.0, 10.0])
            elements.append(
                SpatialElement(type="p", text=f"Feld: {name} ({alt_text})", bbox=bbox)
            )
        CoordinateAdapter.normalize_elements(elements, coord_sys, p_height)
        return elements


class FormulaAdapter:
    @staticmethod
    def parse(raw_data: Dict[str, Any]) -> str:
        return raw_data.get("markdown", "")


class VisionAdapter:
    @staticmethod
    def parse(raw_data: Dict[str, Any]) -> Dict[str, str]:
        return {
            str(k): str(v) for k, v in raw_data.items() if k not in ("status", "error")
        }


class ColumnAdapter:
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
                # 🚀 FIX: text=None statt str(idx) (Verhindert "0" Bug)
                elements.append(SpatialElement(type="column", bbox=bbox, text=None))
            CoordinateAdapter.normalize_elements(elements, coord_sys, p_height)
            result[p_num] = elements
        return result


class HeaderFooterAdapter:
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
                # 🚀 FIX: text=None statt artifact_type (Verhindert Überschreiben)
                elements.append(
                    SpatialElement(
                        type="artifact",
                        bbox=el.get("bbox", [0.0, 0.0, 0.0, 0.0]),
                        text=None,
                    )
                )
            CoordinateAdapter.normalize_elements(elements, coord_sys, p_height)
            result[p_num] = elements
        return result


class CaptionAdapter:
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
                # 🚀 FIX: text=None statt c_type (Vererbt Original-Text aus dem PDF)
                elements.append(
                    SpatialElement(
                        type="caption",
                        bbox=el.get("bbox", [0.0, 0.0, 0.0, 0.0]),
                        text=None,
                    )
                )
            CoordinateAdapter.normalize_elements(elements, coord_sys, p_height)
            result[p_num] = elements
        return result
