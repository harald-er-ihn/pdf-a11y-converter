# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
Text-Aware Bipartite Spatial Matching.
Löst das naive Bounding-Box Kollisionsproblem durch gewichtete
geometrische und semantische Heuristiken.
"""

import re
from difflib import SequenceMatcher
from typing import Dict, List

from src.domain.spatial import SpatialElement
from src.domain.geometry import bbox_iou


class SpatialMatcher:
    """Kapselt die Text-Aware Bipartite Matching Logik für die Sensor-Fusion."""

    THRESHOLD = 0.3
    ALPHA = 0.4
    BETA = 0.6

    @staticmethod
    def _extract_text(el: SpatialElement) -> str:
        """Extrahiert den rohen Text aus einem beliebigen SpatialElement."""
        if el.text:
            return el.text
        if el.html:
            return re.sub(r"<[^>]+>", " ", el.html).strip()
        if el.items:
            return " ".join([i.get("text", "") for i in el.items]).strip()
        return ""

    @classmethod
    def compute_text_similarity(cls, text1: str, text2: str) -> float:
        """Berechnet die deterministische Textähnlichkeit (Levenshtein/SequenceMatcher)."""
        t1, t2 = text1.strip().lower(), text2.strip().lower()
        if not t1 and not t2:
            return 1.0
        if not t1 or not t2:
            return 0.0
        return SequenceMatcher(None, t1, t2).ratio()

    @classmethod
    def compute_weighted_match(cls, el1: SpatialElement, el2: SpatialElement) -> float:
        """Kombiniert Geometrie (IoU) und Semantik (Text Similarity)."""
        iou_score = bbox_iou(el1.bbox, el2.bbox)
        text1 = cls._extract_text(el1)
        text2 = cls._extract_text(el2)

        text_score = cls.compute_text_similarity(text1, text2)

        # Fallback: Wenn beide Elemente keinen Text haben, zählt nur die Geometrie
        if not text1 and not text2:
            return iou_score

        return (cls.ALPHA * iou_score) + (cls.BETA * text_score)

    @classmethod
    def match_elements(
        cls,
        layout_elements: List[SpatialElement],
        worker_elements: List[SpatialElement],
    ) -> Dict[int, int]:
        """
        Erzeugt ein Mapping (layout_idx -> worker_idx) basierend auf dem höchsten Weighted Score.
        Implementiert ein Greedy Bipartite Assignment, bei dem Worker-Elemente (z.B. Tabellen)
        auch mehrere kleine Layout-Elemente absorbieren dürfen.
        """
        mapping: Dict[int, int] = {}

        for l_idx, l_el in enumerate(layout_elements):
            best_score = 0.0
            best_w_idx = -1

            for w_idx, w_el in enumerate(worker_elements):
                score = cls.compute_weighted_match(l_el, w_el)
                if score > best_score:
                    best_score = score
                    best_w_idx = w_idx

            if best_score >= cls.THRESHOLD:
                mapping[l_idx] = best_w_idx

        return mapping
