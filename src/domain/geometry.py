# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
Geometrie-Utility für das Spatial DOM.
Implementiert robuste Kollisionsprüfungen (Intersection over Union).
Verhindert SPOF durch Skalierungs- und OCR-Verschiebungen zwischen Workern.
"""

from typing import List


def bbox_area(bbox: List[float]) -> float:
    """Berechnet die Fläche einer Bounding Box [x0, y0, x1, y1]."""
    width = max(0.0, bbox[2] - bbox[0])
    height = max(0.0, bbox[3] - bbox[1])
    return width * height


def bbox_intersection(b1: List[float], b2: List[float]) -> float:
    """Berechnet die Schnittfläche zweier Bounding Boxes."""
    x_left = max(b1[0], b2[0])
    y_top = max(b1[1], b2[1])
    x_right = min(b1[2], b2[2])
    y_bottom = min(b1[3], b2[3])

    if x_right < x_left or y_bottom < y_top:
        return 0.0

    return (x_right - x_left) * (y_bottom - y_top)


def bbox_iou(b1: List[float], b2: List[float]) -> float:
    """Berechnet die Intersection over Union (IoU) zweier Bounding Boxes."""
    inter = bbox_intersection(b1, b2)
    if inter <= 0.0:
        return 0.0

    union = bbox_area(b1) + bbox_area(b2) - inter
    if union <= 0.0:
        return 0.0

    return inter / union


def bbox_overlap(b1: List[float], b2: List[float], threshold: float = 0.25) -> bool:
    """
    Prüft, ob zwei Bounding Boxes einen definierten IoU-Wert überschreiten.
    """
    return bbox_iou(b1, b2) >= threshold
