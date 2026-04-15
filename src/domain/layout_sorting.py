# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
Topological Layout Sorting (XY-Cut).
Sortiert SpatialElements in die korrekte semantische Lesereihenfolge,
um PDF/UA-Richtlinien (Meaningful Sequence) zu erfüllen.
"""

from typing import List
from src.domain.spatial import SpatialElement


def _x_overlap(bbox1: List[float], bbox2: List[float]) -> float:
    """Gibt die Überlappung auf der X-Achse in Punkten zurück."""
    return max(0.0, min(bbox1[2], bbox2[2]) - max(bbox1[0], bbox2[0]))


def sort_by_columns(elements: List[SpatialElement]) -> List[List[SpatialElement]]:
    """
    Gruppiert Elemente in Spalten basierend auf ihrer X-Koordinate.
    Elemente, die sich horizontal signifikant überschneiden oder
    deren X-Zentren nah beieinander liegen, bilden eine Spalte.
    """
    if not elements:
        return []

    # 1. Elemente initial nach der linken Kante (x0) sortieren
    sorted_by_x = sorted(elements, key=lambda el: el.bbox[0])

    columns: List[List[SpatialElement]] = []
    current_col = [sorted_by_x[0]]

    for el in sorted_by_x[1:]:
        prev_el = current_col[-1]

        # Berechne X-Zentren für Toleranz-Prüfung
        el_center_x = (el.bbox[0] + el.bbox[2]) / 2.0
        prev_center_x = (prev_el.bbox[0] + prev_el.bbox[2]) / 2.0

        overlap = _x_overlap(el.bbox, prev_el.bbox)

        # Heuristik: Wenn sie horizontal überlappen oder auf derselben vertikalen
        # Achse liegen (Toleranz: 100 pt), gehören sie zur gleichen Spalte.
        if overlap > 0 or abs(el_center_x - prev_center_x) < 100.0:
            current_col.append(el)
        else:
            columns.append(current_col)
            current_col = [el]

    if current_col:
        columns.append(current_col)

    return columns


def sort_by_reading_order(elements: List[SpatialElement]) -> List[SpatialElement]:
    """
    XY-Cut Reading Order Algorithmus.
    1. Spalten identifizieren und von links nach rechts sortieren.
    2. Innerhalb der Spalte von oben nach unten (Y) sortieren.
    """
    if not elements:
        return []

    columns = sort_by_columns(elements)
    sorted_elements: List[SpatialElement] = []

    # Sortiere Spalten von links nach rechts (anhand des am weitesten links stehenden Elements)
    columns.sort(key=lambda col: min(el.bbox[0] for el in col))

    for col in columns:
        # Innerhalb der Spalte von oben nach unten sortieren (Y-Achse)
        col.sort(key=lambda el: el.bbox[1])
        sorted_elements.extend(col)

    return sorted_elements
